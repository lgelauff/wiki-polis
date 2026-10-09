# Admin console site map

> **Class: tracks-code reference.** Verified against `9ce71b41` (2026-10-09) by reading the
> routes in `v2/frontend/src/app.tsx`, the pages under `v2/frontend/src/features/admin/`,
> and the API checks they rely on, and by opening each page as an organizer, a moderator
> and a site admin without a role in a local build of that commit, on a consultation with
> access by access code and one with an invitation list.

Where every admin page lives, who may open it, and where the old addresses lead. The
routes are defined in `v2/frontend/src/app.tsx`; the server serves them as app pages
through `_SPA_ROUTE_PATTERNS` in `v2/app.py`. A page address grants nothing by itself:
what a page shows comes from the API, and which API call needs which role is in
[`route_authorization_matrix.md`](route_authorization_matrix.md). Keep this page in step
when a route is added, moved or removed.

**Roles:**
- **Site admin**: the whole site. The site admin column below is what the code does
  today: a site admin passes every consultation's checks, with or without a role there.
  The admin console specification (epic #473, not in this repository) meant to keep site
  admins out of a consultation's contents unless they hold a role on it.
- **Organizer**: one consultation.
- **Moderator**: one consultation. An organizer passes every check a moderator passes.

**Everyone else**, including people signed in with no role, gets the access page ("Not
allowed"). Signed out, Admin home (`/admin`) sends them to the login and back; the other
admin pages show the access page.

## Site level

| Address | Page | Who can open it |
|---|---|---|
| `/admin` | **Admin home**: the consultations where you hold a role, with your role, the status, open flags and statements awaiting moderation | anyone with a role, and site admins (a site admin with no role sees an empty list and the link to the dashboard) |
| `/site-admin` | **Site admin dashboard**: all consultations, the Practice Environment, new consultation, site admins | site admins |

## One consultation: `/admin/conversations/<id>`

The sidebar has four sections: Overview, Settings, Moderation and Content. The pages of
Settings, Moderation and Content carry a tab strip; the bare section address opens the
first tab. The sidebar's Settings link opens Basics, its Moderation link opens Flags (the
address in the lifecycle DTO is the old `…/flags`), and its Content link opens
Statements. The Settings tabs are Basics · Access · Invitations · Access codes · Roles;
Access codes is there only when access is by access code. The Overview links to none of
these pages itself: the sidebar and the tab strips reach every one of them, for every
role.

| Sidebar | Tab | Address | Organizer | Moderator | Site admin |
|---|---|---|---|---|---|
| Overview | (none) | `…/<id>` | phase stepper and statistics; readiness and Move on; roles (list); configuration; no links to other pages | phase stepper and statistics; no phase controls, only "Only an organizer or site admin can change phases" and, when a transition is scheduled, when the next phase starts; roles (list) | as organizer, plus Pause, scheduling the next phase, the advanced phase controls, adding and removing roles, and "Ending the consultation" (publish the final report, delete) |
| Settings | Basics | `…/settings` → `…/settings/basics` | edit, one Save | read-only (strict moderation as text) | edit, one Save; also the Practice Environment section |
| | Access | `…/settings/access` | edit, one Save | read-only | edit, one Save |
| | Invitations | `…/settings/invitations` (always a tab) | the list, Remove, and adding. While access is not an invitation list the tab looks the same but its content is greyed: a "not in effect" note on top, adding disabled, the list muted; Remove still works | the list with usernames, read-only (greyed the same way when not in effect) | as organizer |
| | Access codes | `…/settings/vouchers` (a tab only when access is by access code, next to Invitations; the address keeps the earlier word "voucher") | "Also coming" only | the same | the same |
| | Roles | `…/settings/roles` | the list | the list | the list, and change roles |
| Moderation | Queue | `…/moderation` → `…/moderation/queue` | approve, hide | approve, hide | as organizer |
| | Flags | `…/moderation/flags` | mark as handled, with a note | mark as handled, with a note | as organizer |
| | Featured | `…/moderation/featured` | add by statement number, remove; hide, unhide or delete arguments | the same | as organizer |
| | People | `…/moderation/people` (pseudonyms only) | block, unblock | block, unblock | as organizer |
| Content | Statements | `…/content` → `…/content/statements` | approve, hide, back to unmoderated; add and import seed statements (before any phase is open, and while statement submission is open) | the same | as organizer |
| | Participants | `…/content/participants` | usernames; block, unblock | pseudonyms only; block, unblock | as organizer |
| (none) | Delete | `…/termination` (no console page links to it; the Overview has its own Delete) | access page | access page | the delete page; deletes only a consultation with no valid votes |

## Old addresses (bookmarks keep working)

| Old address | Now |
|---|---|
| `/app/admin` | `/site-admin` |
| `/app/admin/conversations/<id>/…` | the current pages also answer under `/app/admin/conversations/<id>/…` (Overview, every Settings, Moderation and Content tab, and `…/termination`) |
| `…/statements` | `…/content/statements` |
| `…/participants` | `…/content/participants` |
| `…/flags` | `…/moderation/flags` |
| `…/featured` | `…/moderation/featured` |
| `/admin/conversations/<id>/invites`, `/app/admin/conversations/<id>/invitations` | `…/settings/invitations` |
| `…/roles` | `…/settings/roles` |
| `/app/admin/conversations/<id>/moderation` | `…/moderation/flags` (under `/admin/…`, `…/moderation` opens Queue) |

`…/statements`, `…/participants`, `…/featured` and `…/roles` redirect under both `/admin/`
and `/app/admin/`; `…/flags` only under `/admin/`. Every redirect of a consultation page
lands under `/admin/conversations/<id>/` and keeps the query string and the `#fragment`.

## Ways in

- **From the participant site:** the "You moderate" list on the home page has an Admin
  link per consultation: the consultations where you hold a role, and every consultation
  for a site admin.
- **From the participant header:** an "admin" link to Admin home, shown to site admins only.
- **Inside the console:** the "Admin" mark at the top of the sidebar goes to Admin home
  (on Admin home itself it is plain text). Site admins also have "Site admin dashboard" in
  the sidebar.
