# Privacy & data handling

> DRAFT — not for publication. Pending legal/comms review. This reflects the agreed
> design; commitments below (especially retention) are subject to that review.
> Placeholders marked `pending` need operator/legal input before publishing.

wiki-polis is a deliberation tool for the Wikimedia community. This page explains what
we collect, how your participation is kept private, and how long we keep it.

## What we collect

- Your Wikimedia login (username and user ID), through Wikimedia OAuth — no password.
- A pseudonym you choose for each conversation.
- The opinions you submit — your votes, and any statements or arguments. We call these
  collectively your *opinions* below.
- A notification preference, if you set one (see *Email and notifications*).

We never see or store your email address.

## How your opinions stay private

While a conversation is collecting opinions, no one can see who voted what — not other
participants, not the public. Results are shown only in aggregate (opinion groups), and
your opinions appear under your pseudonym, never your name. This keeps opinions
independent.

## Pseudonyms

Each conversation gives you a different pseudonym from a generated list. A pseudonym is
unique across the whole platform and is never reused, so it cannot be used to track you
from one conversation to another.

## What the pseudonym does — and does not — protect

Your opinions are stored in the deliberation engine (Polis) under a one-way hash of your
Wikimedia user ID, not your name. This is a separation, not anonymity: Wikimedia user
IDs are public, so the hash is not cryptographically anonymous.

Only the platform managers could theoretically connect your username with the opinions
you have expressed. That link exists mainly for technical reasons — for example, making
sure each person participates once (deduplication). It is never shown to other
participants or to the public.

## Email and notifications

If you opt in to email updates we do **not** receive your email address. We only learn
from Wikimedia whether your account can be emailed, and any updates would be sent
through Wikimedia's own email system, which never reveals your address to us.
Notifications are opt-in and best-effort; today we record your preference but do not yet
send any.

## Showing your name (optional, after a conversation closes)

After a conversation closes you may choose to publicly attach your Wikimedia username to
your pseudonym for that conversation. This is voluntary — and once you do it the
connection is permanent: it stays on the record and is not designed to be reversible. If
you never choose this, no such public connection is ever made.

## How long we keep things

- Your opinions (under your pseudonym) are kept so results and any published datasets
  stay valid.
- The internal link between your Wikimedia account and your pseudonym — held only by the
  platform managers, for the technical purposes above — is kept for up to 180 days after
  a conversation closes, then removed. It is never public.
- A public connection you chose to make (above) is permanent, by your choice.
- You cannot ask us to delete the internal link early: otherwise someone could influence
  a consultation and then erase the evidence. The 180-day removal is the mechanism.

> `pending` — confirm this model before publishing. As written, a voluntary reveal is
> *permanent* and the 180-day limit applies only to the *internal* account↔pseudonym
> link. This differs from both `spec_functional-design.md` and the current code, which
> *nullify* revealed links at the retention window. The spec, decision D-PRIV's wording,
> and the code must be reconciled to one model first.

## Your choices

- Whether to reveal your name after a conversation closes is entirely your choice — and
  permanent if you do.
- Email updates are opt-in.

## Who runs this, and changes to this notice

*(pending — data-controller identity, a contact, and how changes to this notice are announced.)*
