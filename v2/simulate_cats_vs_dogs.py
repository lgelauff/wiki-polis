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
  uv run python simulate_cats_vs_dogs.py --skip-flask
"""

import argparse
import random
import re
import string
import subprocess
import sys

import requests

PARTICIAPI  = "http://localhost:8000"
FLASK       = "http://localhost:5001"
DB_CONTAINER = "particiapp-docker-postgres-1"

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
# 1=agree, -1=disagree, 0=pass
VOTES = [
    # Seed statements
    ( 1, -1,  0),  #  0  cats better companions
    (-1,  1,  0),  #  1  dogs more loyal
    ( 1, -1,  1),  #  2  cats easier to care for
    (-1,  1,  1),  #  3  dogs better for families
    ( 1, -1,  1),  #  4  cats cleaner
    (-1,  1,  0),  #  5  dogs better emotional support
    ( 1, -1,  1),  #  6  cats more independent
    (-1,  1,  1),  #  7  dogs motivate exercise
    ( 1, -1,  1),  #  8  cats for apartments
    (-1,  1,  0),  #  9  dogs more affectionate
    # Follow-up statements
    ( 1,  1,  1),  # 10  both can be loving (consensus)
    ( 1, -1,  0),  # 11  dogs require too much time
    ( 1, -1,  0),  # 12  cats more intelligent
    ( 1, -1,  1),  # 13  dogs need garden
    ( 1, -1,  0),  # 14  dogs smell/mess
    (-1,  1,  1),  # 15  dogs better trained
    ( 1,  0,  1),  # 16  cats healthier/longer
    (-1,  1,  1),  # 17  dogs make you social
    ( 1,  0,  1),  # 18  cats less expensive
    (-1,  1,  1),  # 19  dogs for security
    ( 1, -1,  1),  # 20  cats for long work hours
    (-1,  1,  0),  # 21  dogs for mental health
    ( 1,  0,  1),  # 22  cats entertaining
    (-1,  1,  0),  # 23  dogs show empathy
    ( 1,  1,  1),  # 24  pet type matters less (consensus)
]

GROUP_SIZES = [35, 30, 10]   # cat people, dog people, neutral


# ── Helpers ───────────────────────────────────────────────────────────────────

def new_session() -> tuple[str, str]:
    """Create a fresh anonymous Particiapi session. Returns (session_cookie, csrf_token).

    requests honours the Secure flag and won't send the cookie over plain HTTP,
    so we extract the raw value from Set-Cookie and pass it manually.
    """
    r = requests.post(f"{PARTICIAPI}/api/session?create=true")
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


def psql(sql: str) -> str:
    """Run a SQL statement in the Polis PostgreSQL container. Returns first result row."""
    r = subprocess.run(
        ["docker", "exec", DB_CONTAINER,
         "psql", "-U", "polis", "polis", "-t", "-c", sql],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    # -t gives tuples-only output: value lines come first, then status like "INSERT 0 1"
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip() and not l.strip().startswith(("INSERT", "UPDATE", "DELETE", "SELECT"))]
    return lines[0] if lines else ""


def create_polis_conversation(topic: str, description: str) -> str:
    """Insert a new conversation directly into Polis PostgreSQL. Returns zinvite."""
    zinvite = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    zid = psql(
        f"INSERT INTO conversations "
        f"(topic, description, owner, is_active, is_public, write_type, vis_type) "
        f"VALUES ($$%s$$, $$%s$$, 1, true, true, 1, 1) RETURNING zid;" % (topic, description)
    )
    psql(f"INSERT INTO zinvites (zid, zinvite) VALUES ({zid}, '{zinvite}');")
    return zinvite


def register_in_flask(zinvite: str) -> None:
    """Register the conversation in the wiki-polis Flask DB."""
    base_slug = f"cats-vs-dogs-{zinvite[:6]}"
    s = requests.Session()
    r = s.get(f"{FLASK}/dev-login?username=DevUser", allow_redirects=True)
    if r.status_code != 200:
        print(f"  Flask login failed ({r.status_code}) — skipping registration")
        return
    slug = base_slug
    for attempt in range(1, 10):
        r = s.post(f"{FLASK}/admin/conversations/new", allow_redirects=False, data={
            "slug": slug,
            "title": "Cats vs Dogs",
            "polis_id": zinvite,
            "access_policy": "public",
            "intro_text": "Should you own a cat or a dog? Vote on the statements below.",
        })
        if r.status_code in (200, 302):
            break
        if r.status_code == 400:
            slug = f"{base_slug}-{attempt + 1}"
            continue
        print(f"  Flask registration returned {r.status_code}")
        return
    if r.status_code in (200, 302):
        print(f"  Registered: /c/{slug}")
        # Enable submission + public results phases
        # Find the conv_id by slug
        from app import app
        from db import Conversation, db
        with app.app_context():
            conv = Conversation.query.filter_by(slug=slug).first()
            if conv:
                conv.phase_submission   = True
                conv.phase_public_results = True
                db.session.commit()
                print(f"  Phases enabled (submission + public results)")


# ── Main simulation ───────────────────────────────────────────────────────────

def run_simulation(conv_id: str) -> None:
    """
    Realistic rolling simulation:

    1. Pre-load seed statements via an admin session (before any participants arrive).
    2. Process 75 participants in sequence.  Each participant:
       - Sees only the statements that existed when they arrived (sparse matrix).
       - Votes on all of them in a random order with group-consistent noise.
       - If assigned as a "submitter", inserts their follow-up at a random mid-vote
         point; the statement then becomes visible to all subsequent participants.
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

    # ── Step 2: rolling participants ──────────────────────────────────────────
    print(f"\n[2/2] Running {N} participants "
          f"({GROUP_SIZES[0]} cat / {GROUP_SIZES[1]} dog / {GROUP_SIZES[2]} neutral)…")

    # Group assignment per participant slot
    groups = [0]*GROUP_SIZES[0] + [1]*GROUP_SIZES[1] + [2]*GROUP_SIZES[2]
    random.shuffle(groups)

    # Randomly assign 15 participant slots as submitters (one follow-up each)
    submitter_slots = sorted(random.sample(range(N), len(FOLLOWUP_STATEMENTS)))
    followup_for: dict[int, int] = {slot: idx for idx, slot in enumerate(submitter_slots)}

    total_votes   = 0
    total_skipped = 0

    for p_idx in range(N):
        group_idx    = groups[p_idx]
        cookie, csrf = new_session()
        snapshot     = list(pool)          # statements visible on arrival
        followup_idx = followup_for.get(p_idx)

        if followup_idx is not None:
            # Split snapshot at a random point; submit the follow-up between the halves
            random.shuffle(snapshot)
            split   = random.randint(0, len(snapshot))
            batch1  = snapshot[:split]
            batch2  = snapshot[split:]

            for tid, votes_idx in batch1:
                raw  = VOTES[votes_idx][group_idx] if votes_idx < len(VOTES) else 0
                if cast_vote(cookie, csrf, conv_id, tid, add_noise(raw)):
                    total_votes += 1
                else:
                    total_skipped += 1

            text    = FOLLOWUP_STATEMENTS[followup_idx]
            new_tid = submit_statement(cookie, csrf, conv_id, text)
            if new_tid is not None:
                pool.append((new_tid, 10 + followup_idx))
                print(f"  [p{p_idx+1:02d}] submitted tid={new_tid}  {text[:55]}")

            for tid, votes_idx in batch2:
                raw  = VOTES[votes_idx][group_idx] if votes_idx < len(VOTES) else 0
                if cast_vote(cookie, csrf, conv_id, tid, add_noise(raw)):
                    total_votes += 1
                else:
                    total_skipped += 1

        else:
            random.shuffle(snapshot)
            for tid, votes_idx in snapshot:
                raw  = VOTES[votes_idx][group_idx] if votes_idx < len(VOTES) else 0
                if cast_vote(cookie, csrf, conv_id, tid, add_noise(raw)):
                    total_votes += 1
                else:
                    total_skipped += 1

        if (p_idx + 1) % 15 == 0:
            pct = (p_idx + 1) / N * 100
            print(f"  {p_idx+1}/{N} participants done ({pct:.0f}%) "
                  f"— {len(pool)} statements in pool")

    print(f"\n  → {total_votes} votes cast"
          + (f", {total_skipped} skipped" if total_skipped else "")
          + f", {len(pool)} statements total")

    print(f"\n{'=' * 62}")
    print(f"Simulation complete.")
    print(f"  Polis conversation: {conv_id}")
    print(f"  Particiapi results: {PARTICIAPI}/api/conversations/{conv_id}/results/")
    print(f"  (Polis math runs in the background — typically 30–60 s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conversation-id", metavar="ZINVITE",
                        help="Use an existing Polis conversation instead of creating one")
    parser.add_argument("--skip-flask", action="store_true",
                        help="Skip wiki-polis Flask DB registration")
    args = parser.parse_args()

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

    try:
        run_simulation(conv_id)
    except requests.ConnectionError:
        print("Error: cannot reach Particiapi at http://localhost:8000")
        print("Is the particiapp-docker stack running?  docker compose up")
        sys.exit(1)


if __name__ == "__main__":
    random.seed()  # non-deterministic each run
    main()
