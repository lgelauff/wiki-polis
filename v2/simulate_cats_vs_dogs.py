#!/usr/bin/env python3
"""
simulate_cats_vs_dogs.py — Generate a Cats vs Dogs deliberation for local testing.

Creates a fresh Polis conversation via direct PostgreSQL insert, pre-loads 10 seed
statements, then runs 75 participants (cat people, dog people, and neutral) through
a realistic rolling simulation:

  - Participants arrive in sequence and vote on whatever statements exist at that moment.
  - 15 of the 75 are "submitters": they add one of the follow-up statements at a random
    mid-vote point, so it only appears in the pool for participants who arrive later.
  - This produces the natural sparse vote matrix that Polis PCA is designed for.

Requires:
  - particiapp-docker stack running (docker compose up)
  - wiki-polis Flask app running on port 5001 (uv run flask run --port 5001)

Usage (from v2/ directory):
  uv run python simulate_cats_vs_dogs.py
  uv run python simulate_cats_vs_dogs.py --conversation-id <existing_zinvite>
  uv run python simulate_cats_vs_dogs.py --particiapi-url http://127.0.0.1:8002
  uv run python simulate_cats_vs_dogs.py --skip-flask
  uv run python simulate_cats_vs_dogs.py --phase6   # also advance into informed voting
"""

import argparse
import os
import random
import re
import string
import subprocess
import uuid
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

PARTICIAPI  = os.environ.get("PARTICIAPI_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
FLASK       = os.environ.get("WIKI_POLIS_FLASK_URL", "http://127.0.0.1:5001").rstrip("/")
# Overridable: container names collide across stacks on a shared host, and psql()
# below writes. Pin it explicitly rather than trusting the default to be local.
DB_CONTAINER = os.environ.get("POLIS_DB_CONTAINER", "particiapp-docker-postgres-1")

# Trusted-subject secret. When set (and honoured by the Particiapi image), each
# simulated person keeps ONE Polis uid across sessions and across the Phase 2 and
# Phase 6 conversations — which is what production does, and what any analysis
# comparing the two rounds needs. Without it Particiapi mints a throwaway uid per
# session and the two rounds cannot be linked. See ref_cross-device-identity.md.
SUB_SECRET = (os.environ.get("PARTICIAPI_SUB_SECRET")
              or os.environ.get("TRUSTED_SUB_SECRET") or "")
STABLE_IDENTITY = False   # set by probe_stable_identity()

# ── Statements ────────────────────────────────────────────────────────────────

SEED_STATEMENTS = [
    "Cats make better companions than dogs",
    "Dogs are more loyal than cats",
    "Cats are easier to care for than dogs",
    "Dogs are better for families with young children",
    "Cats are cleaner animals than dogs",
    "Dogs provide better emotional support",
    "Cats are more independent and less demanding",
    "Dogs motivate their owners to exercise and stay active",
    "Cats are better suited for apartment living",
    "Dogs are more affectionate than cats",
]

FOLLOWUP_STATEMENTS = [
    "Both cats and dogs can be equally loving companions",
    "Dogs require too much time and attention",
    "Cats are more intelligent than people commonly assume",
    "Dog ownership is only suitable if you have a garden",
    "The smell and mess of dogs is a significant drawback",
    "Dogs can be trained to a much higher level than cats",
    "Cats are generally healthier and live longer than dogs",
    "Owning a dog makes you more social and connected to others",
    "Keeping a cat is less expensive than keeping a dog",
    "Dogs provide a greater sense of security and safety",
    "Cats are the better choice for people who work long hours",
    "Dog ownership does more for your mental health than cat ownership",
    "Cats are more entertaining and fun to observe",
    "Dogs show more empathy and awareness of their owner's emotions",
    "Having a pet matters more than which species you choose",
]

# ── Voting patterns ────────────────────────────────────────────────────────────
# One tuple per statement: (cat_group, dog_group, neutral_group)
# Polis-native signs: -1=agree, 1=disagree, 0=pass. These go to Particiapi verbatim
# (cast_vote does not translate, and neither does Particiapi), so they must be written
# in the convention Polis stores — the same one _cast_informed_votes uses. Authoring
# them the intuitive way round is how phase 2 came to store every agree as a disagree.
VOTES = [
    # Seed statements
    (-1,  1,  0),  #  0  cats better companions
    ( 1, -1,  0),  #  1  dogs more loyal
    (-1,  1, -1),  #  2  cats easier to care for
    ( 1, -1, -1),  #  3  dogs better for families
    (-1,  1, -1),  #  4  cats cleaner
    ( 1, -1,  0),  #  5  dogs better emotional support
    (-1,  1, -1),  #  6  cats more independent
    ( 1, -1, -1),  #  7  dogs motivate exercise
    (-1,  1, -1),  #  8  cats for apartments
    ( 1, -1,  0),  #  9  dogs more affectionate
    # Follow-up statements
    (-1, -1, -1),  # 10  both can be loving (consensus)
    (-1,  1,  0),  # 11  dogs require too much time
    (-1,  1,  0),  # 12  cats more intelligent
    (-1,  1, -1),  # 13  dogs need garden
    (-1,  1,  0),  # 14  dogs smell/mess
    ( 1, -1, -1),  # 15  dogs better trained
    (-1,  0, -1),  # 16  cats healthier/longer
    ( 1, -1, -1),  # 17  dogs make you social
    (-1,  0, -1),  # 18  cats less expensive
    ( 1, -1, -1),  # 19  dogs for security
    (-1,  1, -1),  # 20  cats for long work hours
    ( 1, -1,  0),  # 21  dogs for mental health
    (-1,  0, -1),  # 22  cats entertaining
    ( 1, -1,  0),  # 23  dogs show empathy
    (-1, -1, -1),  # 24  pet type matters less (consensus)
]

GROUP_SIZES = [35, 30, 10]   # cat people, dog people, neutral

# ── Derivative statements (#143 provenance) ───────────────────────────────────
# Rewordings of a seed statement, submitted mid-run as "an improvement on" their
# parent. Each is (index into SEED_STATEMENTS, reworded text). They express the
# same proposition as the parent, so simulated voters vote them the parent's way —
# which is what makes a lineage look like a lineage in the vote matrix.
DERIVATIVE_STATEMENTS = [
    (0, "Cats make better companions than dogs for most households"),
    (1, "Dogs show their loyalty more openly than cats do"),
    (2, "Cats need less daily care than dogs"),
    (3, "Dogs suit families with young children better than cats do"),
    (4, "Cats keep themselves cleaner than dogs do"),
    (8, "Cats adapt to apartment living better than dogs"),
]

# ── Seeded arguments for featured statements ──────────────────────────────────
# Maps statement text → {'pro': [...], 'con': [...]}
# proposer_id=None marks these as admin-seeded (not participant-authored).
# Two arguments per side satisfies the default K=2 importance-voting threshold.

FEATURED_ARGS = {
    "Cats make better companions than dogs": {
        'pro': [
            "Cats provide calm, low-maintenance company that suits people who live alone or work from home.",
            "Unlike dogs, cats don't require constant attention, which respects the owner's time and space.",
        ],
        'con': [
            "Dogs actively engage with their owners and respond to emotions — cats are mostly indifferent.",
            "Dog owners consistently report lower loneliness scores; cats don't create the same social bond.",
        ],
    },
    "Dogs are more loyal than cats": {
        'pro': [
            "Dogs evolved as pack animals and transfer that unconditional loyalty to their human family.",
            "A dog waits at the door for hours; most cats barely acknowledge an owner's return.",
        ],
        'con': [
            "Cats form genuine attachments — they just express them on their own terms, not on demand.",
            "Loyalty that requires continuous reinforcement with treats and commands is trained behaviour, not devotion.",
        ],
    },
    "Cats are easier to care for than dogs": {
        'pro': [
            "Cats self-groom, use a litter box, and can be left alone for a full working day without issue.",
            "The time and financial cost of cat ownership is significantly lower than for dogs of comparable size.",
        ],
        'con': [
            "Lower maintenance does not mean easier — litter box upkeep is unpleasant and easy to neglect.",
            "Dogs adapt their schedule to yours; cats impose their own routine regardless of what the owner needs.",
        ],
    },
    "Dogs are better for families with young children": {
        'pro': [
            "Dogs are patient and gentle with children and actively participate in play in a way cats rarely do.",
            "Growing up with a dog teaches children responsibility, empathy, and respect for animals' boundaries.",
        ],
        'con': [
            "Dogs can bite when startled or stressed, posing a real safety risk around toddlers who can't read warning signs.",
            "A cat's calmer temperament often makes it a safer choice for homes with very young children.",
        ],
    },
    "Dogs are more affectionate than cats": {
        'pro': [
            "Dogs consistently seek physical contact, make eye contact, and show excitement at their owner's presence.",
            "The neurochemistry of dogs is similar to humans in ways that support genuine emotional bonding.",
        ],
        'con': [
            "Cat affection is freely given rather than performed — a purring cat on your lap chose to be there.",
            "Measuring affection by enthusiasm conflates neediness with love; cats bond deeply without requiring constant validation.",
        ],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def subject_for(conv_id: str, person_idx: int) -> str:
    """Stable synthetic subject for one simulated person, scoped to this run so
    repeated runs don't merge into each other's participants."""
    return f"sim-{conv_id}-p{person_idx}"


def new_session(subject: str | None = None) -> tuple[str, str]:
    """Create a Particiapi session. Returns (session_cookie, csrf_token).

    With `subject` (and a working trusted-sub secret) Particiapi resolves the same
    uid every time, the way Flask's proxy does in production. Otherwise it mints a
    fresh anonymous uid, which is fine for single-round tests but leaves Phase 2 and
    Phase 6 participants unlinkable.

    requests honours the Secure flag and won't send the cookie over plain HTTP,
    so we extract the raw value from Set-Cookie and pass it manually.
    """
    headers = {}
    if subject and SUB_SECRET and STABLE_IDENTITY:
        headers = {"X-Particiapi-Sub": subject,
                   "X-Particiapi-Sub-Secret": SUB_SECRET}
    r = requests.post(f"{PARTICIAPI}/api/session?create=true", headers=headers)
    r.raise_for_status()
    m = re.search(r'session=([^;]+)', r.headers.get('Set-Cookie', ''))
    if not m:
        raise RuntimeError(f"No session cookie in response: {r.headers}")
    return m.group(1), r.json()["csrf_token"]


def _headers(session_cookie: str, csrf: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        "Cookie": f"session={session_cookie}",
    }


def submit_statement(session_cookie, csrf, conv_id, text) -> int | None:
    """Submit a statement. Returns the assigned tid, or None on failure."""
    r = requests.post(
        f"{PARTICIAPI}/api/conversations/{conv_id}/statements/",
        headers=_headers(session_cookie, csrf),
        json={"text": text},
    )
    if r.status_code == 201:
        return r.json()["id"]
    if r.status_code == 409:
        print(f"    Duplicate skipped: {text[:55]}")
        return None
    print(f"    Statement failed ({r.status_code}): {r.text[:80]}")
    return None


def cast_vote(session_cookie, csrf, conv_id, tid, value) -> bool:
    """Cast a single vote. Returns True on success."""
    r = requests.put(
        f"{PARTICIAPI}/api/conversations/{conv_id}/votes/{tid}",
        headers=_headers(session_cookie, csrf),
        json={"value": value},
    )
    return r.status_code == 200


def add_noise(vote: int, flip_prob: float = 0.12, pass_prob: float = 0.08) -> int:
    """Add realistic noise to a deterministic group vote."""
    if vote == 0:
        return 0
    if random.random() < pass_prob:
        return 0
    if random.random() < flip_prob:
        return -vote
    return vote


def psql(sql: str, **params: str) -> str:
    """Run a SQL statement in the Polis PostgreSQL container. Returns first result row.

    Pass caller-supplied values as keyword arguments and reference them as :\'name\'
    in `sql`; psql quotes them itself. The text that actually needs this is the
    conversation topic and description below — under --phase6 the topic is built
    from `conv.title`, which an admin edits, and a `$$` in it would otherwise
    terminate the dollar quote it used to be pasted into.
    """
    var_args: list[str] = []
    for name, value in params.items():
        var_args += ["-v", f"{name}={value}"]
    # The SQL goes in on stdin, not as -c: psql only interpolates :\'name\' while
    # lexing input it reads, and silently does not do it for -c (which fails with
    # "syntax error at or near \":\"" instead).
    #
    # ON_ERROR_STOP is what makes reading from stdin safe. Without it psql reports
    # a failed statement on stderr and still exits 0, so the returncode check below
    # never fires and the caller reads "" as though it were a value. Measured
    # against postgres:18-trixie: a bad statement via -c exits 1, via stdin exits
    # 0, via stdin with ON_ERROR_STOP exits 3. It goes ahead of *var_args so a
    # caller's parameter cannot shadow it.
    r = subprocess.run(
        ["docker", "exec", "-i", DB_CONTAINER,
         "psql", "-U", "polis", "polis", "-t", "-v", "ON_ERROR_STOP=1", *var_args],
        input=sql, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    # -t gives tuples-only output: value lines come first, then status like "INSERT 0 1"
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip() and not l.strip().startswith(("INSERT", "UPDATE", "DELETE", "SELECT"))]
    return lines[0] if lines else ""


def probe_stable_identity() -> bool:
    """Check whether this Particiapi honours X-Particiapi-Sub, and set STABLE_IDENTITY.

    Opens one session with a throwaway subject and looks for the resulting
    `particiapi_users` row. A `TRUSTED_SUB_SECRET` that is unset, mismatched, or
    absent from the running image all present the same way — a silently anonymous
    session — so this asks the database rather than trusting the response.
    """
    global STABLE_IDENTITY
    if not SUB_SECRET:
        print("  [identity] PARTICIAPI_SUB_SECRET unset — participants will be "
              "anonymous and Phase 2/Phase 6 cannot be linked")
        STABLE_IDENTITY = False
        return False

    # Unique per run. A fixed subject is satisfied by a row that some earlier run
    # left behind, so the probe would keep reporting success after the secret was
    # rotated or the image swapped for one without trusted-sub — and since a
    # mismatched secret degrades to an anonymous session with a 200, nothing else
    # would catch it either. The row this leaves behind has no participants or
    # votes rows, so it joins to nothing.
    probe = f"sim-identity-probe-{uuid.uuid4().hex[:12]}"
    try:
        requests.post(f"{PARTICIAPI}/api/session?create=true",
                      headers={"X-Particiapi-Sub": probe,
                               "X-Particiapi-Sub-Secret": SUB_SECRET}).raise_for_status()
        found = psql("SELECT COUNT(*) FROM particiapi_users WHERE subject = :'s';",
                     s=probe)
        STABLE_IDENTITY = found.strip() not in ("", "0")
    except Exception as e:
        print(f"  [identity] probe failed ({e}) — falling back to anonymous sessions")
        STABLE_IDENTITY = False
        return False

    if STABLE_IDENTITY:
        print("  [identity] trusted-sub honoured — participants keep one uid across rounds")
    else:
        print("  [identity] trusted-sub NOT honoured (secret mismatch, or a Particiapi "
              "image predating the feature) — participants will be anonymous")
    return STABLE_IDENTITY


def record_provenance(conv_id: str, new_tid: int, parent_tid: int,
                      new_text: str, parent_text: str) -> bool:
    """Record `new_tid` as a declared improvement on `parent_tid` in the Flask DB.

    Calls the app's own `record_statement_provenance`, so the row and its similarity
    scores are written by exactly the code the /statements/new route uses. (The route
    itself needs an OAuth session and CSRF, which this simulator has no way to hold.)
    """
    try:
        from app import app, record_statement_provenance
        from db import Conversation
        with app.app_context():
            conv = Conversation.query.filter_by(polis_id=conv_id).first()
            if conv is None:
                return False
            row = record_statement_provenance(
                conv.id, new_tid, parent_tid,
                parent_text=parent_text, new_text=new_text)
            return row is not None
    except Exception as e:
        print(f"    [warn] provenance write failed for tid={new_tid}: {e}")
        return False


def create_polis_conversation(topic: str, description: str) -> str:
    """Insert a new conversation directly into Polis PostgreSQL. Returns zinvite."""
    zinvite = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    zid = psql(
        "INSERT INTO conversations "
        "(topic, description, owner, is_active, is_public, write_type, vis_type) "
        "VALUES (:'topic', :'descr', 1, true, true, 1, 1) RETURNING zid;",
        topic=topic, descr=description)
    if not zid:
        raise RuntimeError("conversation insert returned no zid")
    psql("INSERT INTO zinvites (zid, zinvite) VALUES (:'zid', :'zinvite');",
         zid=zid, zinvite=zinvite)
    return zinvite


def seed_featured_statements(conv_id: str, text_to_tid: dict) -> None:
    """Create FeaturedStatement + seeded Argument records in the Flask DB."""
    from app import app
    from db import Argument, Conversation, FeaturedStatement, db as flask_db
    with app.app_context():
        conv = Conversation.query.filter_by(polis_id=conv_id).first()
        if not conv:
            print("  [skip] conversation not found in Flask DB")
            return

        fs_count = arg_count = 0
        for text, sides in FEATURED_ARGS.items():
            tid = text_to_tid.get(text)
            if tid is None:
                print(f"  [skip] tid not found for: {text[:60]}")
                continue

            fs = FeaturedStatement.query.filter_by(
                conversation_id=conv.id, polis_statement_id=tid).first()
            if not fs:
                fs = FeaturedStatement(
                    conversation_id=conv.id,
                    polis_statement_id=tid,
                    confirmed_by_admin=True,
                    statement_text=text,
                )
                flask_db.session.add(fs)
                flask_db.session.flush()
                fs_count += 1

            for side in ('pro', 'con'):
                for body in sides[side]:
                    exists = Argument.query.filter_by(
                        featured_statement_id=fs.id, body=body, side=side).first()
                    if not exists:
                        flask_db.session.add(Argument(
                            featured_statement_id=fs.id,
                            proposer_pseudonym=None,   # NULL = admin-seeded
                            body=body,
                            side=side,
                        ))
                        arg_count += 1

        flask_db.session.commit()
        print(f"  Seeded {fs_count} featured statement(s), {arg_count} argument(s)")


def register_in_flask(zinvite: str) -> None:
    """Register the conversation in the wiki-polis Flask DB directly via SQLAlchemy."""
    from app import app
    from db import Conversation, db as flask_db
    base_slug = f"cats-vs-dogs-{zinvite[:6]}"
    with app.app_context():
        slug = base_slug
        for attempt in range(1, 10):
            if not Conversation.query.filter_by(slug=slug).first():
                break
            slug = f"{base_slug}-{attempt + 1}"

        conv = Conversation(
            slug=slug,
            polis_id=zinvite,
            title='Cats vs Dogs',
            intro_text='Should you own a cat or a dog? Vote on the statements below.',
            access_policy='public',
            active=True,
            phase_submission=True,
            phase_personal_results=True,
            phase_argument_mapping=True,
            phase_public_results=True,
        )
        flask_db.session.add(conv)
        flask_db.session.commit()
        print(f"  Registered: /c/{slug}  (all phases enabled)")


# ── Main simulation ───────────────────────────────────────────────────────────

def run_simulation(conv_id: str, n_derivatives: int = 0) -> None:
    """
    Realistic rolling simulation:

    1. Pre-load seed statements via an admin session (before any participants arrive).
    2. Process 75 participants in sequence.  Each participant:
       - Sees only the statements that existed when they arrived (sparse matrix).
       - Votes on all of them in a random order with group-consistent noise.
       - If assigned as a "submitter", inserts their follow-up at a random mid-vote
         point; the statement then becomes visible to all subsequent participants.
       - Some submitters instead post a *derivative*: a reworded version of an
         existing statement, linked to its parent in `statement_provenance`.
    """
    N = sum(GROUP_SIZES)
    print(f"\nConversation: {conv_id}")
    print("=" * 62)

    # ── Step 1: seed statements ───────────────────────────────────────────────
    print(f"\n[1/2] Submitting {len(SEED_STATEMENTS)} seed statements...")
    admin_cookie, admin_csrf = new_session()
    # pool entries: (tid, votes_row_index)
    pool: list[tuple[int, int]] = []
    for i, text in enumerate(SEED_STATEMENTS):
        tid = submit_statement(admin_cookie, admin_csrf, conv_id, text)
        if tid is not None:
            pool.append((tid, i))
            print(f"  tid={tid}  {text}")
    print(f"  → {len(pool)} seed statements in pool")
    tid_by_seed_idx = {votes_idx: tid for tid, votes_idx in pool}
    derivative_tids: set[int] = set()

    # ── Step 2: rolling participants ──────────────────────────────────────────
    print(f"\n[2/2] Running {N} participants "
          f"({GROUP_SIZES[0]} cat / {GROUP_SIZES[1]} dog / {GROUP_SIZES[2]} neutral)…")

    # Group assignment per participant slot
    groups = [0]*GROUP_SIZES[0] + [1]*GROUP_SIZES[1] + [2]*GROUP_SIZES[2]
    random.shuffle(groups)

    # Randomly assign submitter slots: one follow-up each, plus n_derivatives slots
    # that post a reworded version of an existing statement instead.
    n_derivatives = max(0, min(n_derivatives, len(DERIVATIVE_STATEMENTS)))
    slots = random.sample(range(N), len(FOLLOWUP_STATEMENTS) + n_derivatives)
    followup_for: dict[int, int] = {
        slot: idx for idx, slot in enumerate(sorted(slots[:len(FOLLOWUP_STATEMENTS)]))}
    derivative_for: dict[int, int] = {
        slot: idx for idx, slot in enumerate(sorted(slots[len(FOLLOWUP_STATEMENTS):]))}

    total_votes   = 0
    total_skipped = 0
    total_linked  = 0

    for p_idx in range(N):
        group_idx    = groups[p_idx]
        cookie, csrf = new_session(subject_for(conv_id, p_idx))
        snapshot     = list(pool)          # statements visible on arrival

        # What this participant submits mid-vote, if anything:
        #   (text, votes_row_index, parent_tid | None, parent_text | None)
        submission = None
        followup_idx = followup_for.get(p_idx)
        derivative_idx = derivative_for.get(p_idx)
        if followup_idx is not None:
            submission = (FOLLOWUP_STATEMENTS[followup_idx],
                          len(SEED_STATEMENTS) + followup_idx, None, None)
        elif derivative_idx is not None:
            parent_seed_idx, text = DERIVATIVE_STATEMENTS[derivative_idx]
            parent_tid = tid_by_seed_idx.get(parent_seed_idx)
            if parent_tid is not None:
                # A derivative restates its parent, so it inherits the parent's
                # voting row — later arrivals vote on both the same way.
                submission = (text, parent_seed_idx, parent_tid,
                              SEED_STATEMENTS[parent_seed_idx])

        def vote_batch(batch):
            nonlocal total_votes, total_skipped
            for tid, votes_idx in batch:
                raw = VOTES[votes_idx][group_idx] if votes_idx < len(VOTES) else 0
                if cast_vote(cookie, csrf, conv_id, tid, add_noise(raw)):
                    total_votes += 1
                else:
                    total_skipped += 1

        random.shuffle(snapshot)
        if submission is None:
            vote_batch(snapshot)
        else:
            # Split the snapshot at a random point and submit between the halves, so
            # the new statement only exists for participants who arrive later.
            text, votes_idx, parent_tid, parent_text = submission
            split = random.randint(0, len(snapshot))
            vote_batch(snapshot[:split])

            new_tid = submit_statement(cookie, csrf, conv_id, text)
            if new_tid is not None:
                pool.append((new_tid, votes_idx))
                if parent_tid is None:
                    print(f"  [p{p_idx+1:02d}] submitted tid={new_tid}  {text[:55]}")
                else:
                    derivative_tids.add(new_tid)
                    linked = record_provenance(conv_id, new_tid, parent_tid,
                                               text, parent_text)
                    total_linked += bool(linked)
                    mark = "linked" if linked else "UNLINKED"
                    print(f"  [p{p_idx+1:02d}] improved tid={parent_tid} → tid={new_tid} "
                          f"({mark})  {text[:45]}")

            vote_batch(snapshot[split:])

        if (p_idx + 1) % 15 == 0:
            pct = (p_idx + 1) / N * 100
            print(f"  {p_idx+1}/{N} participants done ({pct:.0f}%) "
                  f"— {len(pool)} statements in pool")

    print(f"\n  → {total_votes} votes cast"
          + (f", {total_skipped} skipped" if total_skipped else "")
          + f", {len(pool)} statements total")
    if derivative_tids:
        print(f"  → {len(derivative_tids)} derivative statement(s), "
              f"{total_linked} linked to a parent in statement_provenance")

    print(f"\n{'=' * 62}")
    print("Simulation complete.")
    print(f"  Polis conversation: {conv_id}")
    print(f"  Particiapi results: {PARTICIAPI}/api/conversations/{conv_id}/results/")
    print("  (Polis math runs in the background — typically 30–60 s)")

    # Build text → tid mapping for the caller (used by seed_featured_statements).
    # Derivatives share their parent's votes_idx, so they are skipped here — otherwise
    # a derivative would claim its parent's text and get featured in its place.
    text_to_tid = {}
    for tid, votes_idx in pool:
        if tid in derivative_tids:
            continue
        if votes_idx < len(SEED_STATEMENTS):
            text_to_tid[SEED_STATEMENTS[votes_idx]] = tid
        else:
            fi = votes_idx - len(SEED_STATEMENTS)
            if fi < len(FOLLOWUP_STATEMENTS):
                text_to_tid[FOLLOWUP_STATEMENTS[fi]] = tid
    return text_to_tid


INFORMED_VOTERS = 30


def _cast_informed_votes(p6_zinvite: str, tids: list[int], phase2_conv_id: str) -> None:
    """Cast a batch of grouped informed votes on the Phase 6 statements so the round
    has real cluster structure.

    Writes Polis-native signs directly (-1=agree, +1=disagree, 0=pass): the convention
    every other vote in the system uses, and the one `polis_admin.py` counts as agree.

    The app's informed-vote route wrote the OPPOSITE sign until #328 — agree as +1,
    with nothing negating it downstream — so rounds cast here and rounds cast by
    clicking in the app disagreed. #328 corrected the route and the stored rows on
    production were repaired 2026-09-02, so the two now match. If they ever diverge
    again, this function is the reference: it has always written Polis-native.
    """
    cast = 0
    for v in range(INFORMED_VOTERS):
        g = v % 3                         # three synthetic opinion groups
        # The informed round is voted by the FIRST INFORMED_VOTERS people from Phase 2
        # (same subjects → same uid), so the two rounds can be linked per person.
        cookie, csrf = new_session(subject_for(phase2_conv_id, v))
        for j, tid in enumerate(tids):
            if g == 2:                    # group 2 is noisy/undecided
                val = 0 if random.random() < 0.5 else random.choice((-1, 1))
            else:                         # groups 0/1 take opposite stances per statement
                base = -1 if ((j % 2 == 0) == (g == 0)) else 1
                val = add_noise(base)
            if cast_vote(cookie, csrf, p6_zinvite, tid, val):
                cast += 1
    print(f"  Cast {cast} informed votes across {INFORMED_VOTERS} participants")
    # Say this on stdout, not only in a docstring the operator never opens: anyone
    # comparing this round against one voted through the app needs to know the two
    # currently disagree, or they will read the difference as a bug here.
    print("  [signs] written Polis-native (-1=agree) — the same convention the app's "
          "Phase 6 route uses since #328, so a round cast here and one cast by "
          "clicking in the app now agree.")
    print(f"  [counts] `votes` will hold {cast} rows plus one author agree per "
          "statement — Polis adds those itself; see ref_polis-data-model.md.")


def advance_to_phase6(conv_id: str) -> None:
    """Advance the conversation into Phase 6 (informed voting).

    Creates the dedicated Phase 6 Polis conversation, seeds it with the confirmed
    featured statements (recording each phase6 tid onto the FeaturedStatement row),
    wires the id onto the conversation, flips `phase_informed_voting`, and casts a
    batch of informed votes. Follows the app's `_init_phase6` in outline, but via the
    same raw-SQL + HTTP path the rest of this simulator uses, so it needs no Polis
    admin credentials (which the local dev stack does not set).

    That substitution has one measured consequence. `_init_phase6` seeds through the
    moderator path (`add_seed_return_id`), which leaves a `vote: 0` author row per
    statement; seeding through the participant endpoint as this does leaves a `-1`
    (agree) instead. So a simulated Phase 6 round carries author agrees that
    production does not — confirmed on production 2026-09-02, where the sole Phase 6
    round held 11 author rows, all `vote=0`. See ref_polis-data-model.md."""
    from app import app
    from db import Conversation, FeaturedStatement, db as flask_db
    with app.app_context():
        conv = Conversation.query.filter_by(polis_id=conv_id).first()
        if conv is None:
            print("  [skip] conversation not found in Flask DB")
            return
        featured = (FeaturedStatement.query
                    .filter_by(conversation_id=conv.id, confirmed_by_admin=True)
                    .all())
        if not featured:
            print("  [skip] no confirmed featured statements to seed into Phase 6")
            return

        p6_zinvite = create_polis_conversation(
            f"{conv.title} — Informed Voting",
            "Informed voting round on the featured statements.")
        print(f"  Phase 6 Polis conversation: {p6_zinvite}")

        admin_cookie, admin_csrf = new_session()
        p6_tids: list[int] = []
        for fs in featured:
            tid = submit_statement(admin_cookie, admin_csrf, p6_zinvite, fs.statement_text)
            if tid is None:
                print(f"  [warn] could not seed featured statement fs={fs.id}")
                continue
            fs.phase6_polis_statement_id = tid
            p6_tids.append(tid)

        conv.phase6_polis_conversation_id = p6_zinvite
        conv.phase_informed_voting = True
        flask_db.session.commit()
        print(f"  Seeded {len(p6_tids)} statement(s); phase_informed_voting=True")

        if p6_tids:
            _cast_informed_votes(p6_zinvite, p6_tids, conv_id)


def main():
    global FLASK, PARTICIAPI

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conversation-id", metavar="ZINVITE",
                        help="Use an existing Polis conversation instead of creating one")
    parser.add_argument("--skip-flask", action="store_true",
                        help="Skip wiki-polis Flask DB registration")
    parser.add_argument("--phase6", action="store_true",
                        help="Also advance into Phase 6 (informed voting): create the "
                             "dedicated Polis conversation, seed featured statements, flip "
                             "the phase, and cast informed votes. Requires Flask registration.")
    parser.add_argument("--flask-url", metavar="URL", default=FLASK,
                        help=f"Base URL of the wiki-polis Flask app (default: {FLASK})")
    parser.add_argument("--particiapi-url", metavar="URL", default=PARTICIAPI,
                        help=f"Base URL of Particiapi (default: {PARTICIAPI})")
    parser.add_argument("--derivatives", type=int, default=0,
                        metavar="N",
                        help="Submit N statements as declared improvements on an existing "
                             "statement, recording each in statement_provenance "
                             f"(max {len(DERIVATIVE_STATEMENTS)}). Requires Flask registration.")
    args = parser.parse_args()

    FLASK = args.flask_url.rstrip("/")
    PARTICIAPI = args.particiapi_url.rstrip("/")

    # The default container name is whatever compose generated for *a*
    # particiapp-docker checkout on this host, and POLIS_DB_CONTAINER can also come
    # from v2/.env via load_dotenv. A run that writes into the wrong stack's Polis
    # database otherwise looks identical on stdout to a correct one.
    print(f"Polis DB container: {DB_CONTAINER}   ·   Particiapi: {PARTICIAPI}")

    conv_id = args.conversation_id
    if not conv_id:
        print("Creating new Polis conversation...")
        try:
            conv_id = create_polis_conversation(
                "Cats vs Dogs",
                "Which makes a better pet — cats or dogs?",
            )
        except Exception as e:
            print(f"Error: could not create Polis conversation: {e}")
            print("Is the particiapp-docker stack running?  docker compose up")
            sys.exit(1)
        print(f"Created: zinvite={conv_id}")

        if not args.skip_flask:
            print("Registering in wiki-polis Flask DB...")
            try:
                register_in_flask(conv_id)
            except Exception as e:
                print(f"  Flask registration failed: {e} (continuing anyway)")

    n_derivatives = args.derivatives
    if n_derivatives and args.skip_flask:
        print("\n[skip] --derivatives needs the Flask DB for provenance (drop --skip-flask)")
        n_derivatives = 0

    probe_stable_identity()

    try:
        text_to_tid = run_simulation(conv_id, n_derivatives=n_derivatives)
    except requests.ConnectionError:
        print(f"Error: cannot reach Particiapi at {PARTICIAPI}")
        print("Is the particiapp-docker stack running?  docker compose up")
        sys.exit(1)

    if not args.skip_flask:
        print("\nSeeding featured statements and arguments...")
        try:
            seed_featured_statements(conv_id, text_to_tid)
        except Exception as e:
            print(f"  Featured statement seeding failed: {e} (continuing anyway)")

        if args.phase6:
            print("\nAdvancing into Phase 6 (informed voting)...")
            try:
                advance_to_phase6(conv_id)
            except Exception as e:
                print(f"  Phase 6 setup failed: {e} (continuing anyway)")
    elif args.phase6:
        print("\n[skip] --phase6 requires Flask registration (drop --skip-flask)")


if __name__ == "__main__":
    random.seed()  # non-deterministic each run
    main()
