# Prepaid credits (packs)

Pay once with x402 or MPP, then spend call by call with a token: no wallet signature per call. This suits
backtests and bots that make thousands of calls.

- 1 credit = $1 (USDC).
- Credits never expire and pay for every paid route: finance, premium and cheap.
- Pay-per-call x402 / MPP and the free call are unchanged. Credits are another way to pay, not a replacement.
- The token is a bearer secret, shown once: whoever holds it can spend the balance. If it is lost, a new one can
  be issued to whoever proves control of the wallet that paid (write to aidatatools@proton.me).

| Pack | You pay | Credits | Bonus | Worth |
|---|---|---|---|---|
| Probe (`probe`) | $10 | 10 | +0% | 50 planetary-lines calls, 40 event-calendar years, 166 natal charts or 20 Vedic reports |
| Backtest (`backtest`) | $50 | 60 | +20% | 300 planetary-lines calls, 240 event-calendar years, 1000 natal charts or 120 Vedic reports |
| Quant (`quant`) | $200 | 260 | +30% | 1300 planetary-lines calls, 1040 event-calendar years, 4333 natal charts or 520 Vedic reports |
| Autopilot (`autopilot`) | $1000 | 1400 | +40% | 7000 planetary-lines calls, 5600 event-calendar years, 23333 natal charts or 2800 Vedic reports |

The live list, with these figures, is in `GET /v1/catalog` (`credits` block) and `GET /v1/credits`.

## Buy

```bash
curl -i -X POST https://astro-agent.dev/v1/credits/topup -H 'Content-Type: application/json' -d '{"pack":"backtest"}'
# -> 402 with the x402 offer (PAYMENT-REQUIRED) and the MPP offer (WWW-Authenticate: Payment) for $50.00
```

Pay with either offer and send the same request again: `PAYMENT-SIGNATURE` for x402, or
`Authorization: Payment ...` for MPP. Any x402 or MPP client does this for you.

```python
from x402.http.clients import x402_requests        # same client as for a paid call
r = x402_requests(client).post("https://astro-agent.dev/v1/credits/topup", json={"pack": "backtest"})
token = r.json()["token"]                           # shown ONCE: store it now
```

The answer carries:

- `account`: a public id;
- `token`: the secret, shown once;
- `credited_usd`, `bonus_usd` and `balance_usd`;
- `settlement`: the network, the transaction and the payer.

To add to the same balance, send the token with the next top-up (`X-Credits-Token: <token>`). No new token is
issued.

## Spend

```bash
curl -X POST https://astro-agent.dev/v1/finance/events -H 'Content-Type: application/json' \
  -H "X-Credits-Token: $TOKEN" -d '{"start":"2024-01-01","end":"2024-12-31"}'
```

The route's price is deducted. The result carries `meta.payment.protocol = "credits"`, the new balance in
`meta.payment.credits_balance_usd`, and the same balance in the `X-Credits-Balance` header.

| Case | Answer | Charged |
|---|---|---|
| Balance covers the price | 200, result | the price |
| Balance too low | 402 `CREDITS_INSUFFICIENT`: price, balance, packs, and the x402 / MPP offer for this one call | nothing |
| Unknown, malformed or revoked token | 401 `CREDITS_TOKEN_INVALID` | nothing |
| Credits store unreachable | 503 `CREDITS_UNAVAILABLE` | nothing |
| Invalid input | 400, as always | nothing |

A token never falls back to the free call: sending one means "pay with credits".

## Balance and rotation

- `GET /v1/credits/balance` with `X-Credits-Token` returns:
  - the balance, the totals credited, spent and paid;
  - the last 20 movements;
  - how many calls of each finance or premium route the balance still covers.
- `POST /v1/credits/rotate` with `X-Credits-Token` returns a new token. The old one stops working at once and the
  balance stays.

## Security model

| Requirement | How | Test (`tests/test_credits.py`) |
|---|---|---|
| Never credit without a real settlement | Credits come only from what the x402 facilitator or the MPP SDK reports as **settled**, with a transaction reference. With payments off, top-ups answer 503. | `test_no_payment_no_credit`, `test_failed_settlement_no_credit`, `test_payments_off_means_no_topup`, `test_settlement_without_transaction_is_not_credited` |
| Each payment credits once | `credits:paid:<network>:<tx>` is claimed inside the crediting script, with a per-attempt id. A replay, even onto the same account, gets 409. | `test_replayed_payment_credits_once`, `test_concurrent_replay_credits_exactly_once`, `test_mpp_topup_credits_once` |
| Atomic spend, no double spend | One Lua script checks token → account, checks the balance, decrements and writes the audit entry. Redis runs it atomically. | `test_concurrent_double_spend_never_overdraws` (60 parallel $0.50 calls on $10: exactly 20 pass) |
| Never negative | The check and the decrement happen in the same script. | the same test (final balance 0), `test_insufficient_balance_is_refused_cleanly` |
| Token is a secret | 256 random bits (`astc_` + 43 characters). Only its SHA-256 is stored. It is never logged or echoed. Rotation and operator revocation are available. | `test_the_token_is_never_stored_in_clear`, `test_forged_malformed_and_guessed_tokens_spend_nothing`, `test_rotation_revokes_the_old_token`, `test_revoked_token_cannot_spend_even_mid_flight` |
| Integer money | micro-USD everywhere: 1 credit = 1,000,000, the unit of 6-decimal USDC. No float touches a balance. | `test_money_is_integer_micro_usd`, `test_many_small_spends_are_exact` |
| Bonus decided by the server | The client names a pack and nothing else. The price comes from the server. Its requirement is checked against the pack before settlement, the settled amount after, and credits are looked up from the amount paid. | `test_falsified_amount_bonus_and_credits_fields_are_ignored`, `test_paying_less_than_the_pack_settles_nothing`, `test_requirement_mismatch_is_vetoed_before_settlement`, `test_facilitator_reporting_another_amount_is_not_credited` |
| Free tier independent | Credits never read or write the free counters. A token is never turned into a free call. | `test_spend_deducts_the_exact_price_and_leaves_the_free_call`, `test_short_balance_never_falls_back_to_a_free_call`, `test_free_tier_and_pay_per_call_are_untouched` |
| Audit trail | Append-only streams `credits:audit` and `credits:audit:<account>`. Each entry records the time, the kind, the amount, the balance before and after, and, for a top-up, the pack, the amount paid, the network, the transaction and the payer. | `test_topup_credits_once_with_bonus_and_audit`, `test_spend_deducts_...` |
| Fail closed | No KV or a KV error means nothing is credited and nothing is spent. Every refusal (pack, token, store, balance cap) happens before payment. | `test_kv_down_refuses_before_any_payment`, `test_kv_down_spends_nothing_and_gives_nothing`, `test_balance_cap_is_checked_before_payment` |
| Settled but not written | The write is retried, idempotently. If it still fails, the payment is logged as `CREDITS_UNAPPLIED` (without the token), and the buyer gets 502 `CREDITS_PENDING` with the reference and the token. The operator then credits it once with `scripts/credits_admin.py reconcile`. | `test_credit_write_is_retried_then_reported_and_reconciled_once`, `test_lost_answer_is_retried_without_crediting_twice` |

One account holds at most $10,000.

The tests run the production Lua on fakeredis with a real Lua interpreter: `pip install -r requirements-dev.txt`.

