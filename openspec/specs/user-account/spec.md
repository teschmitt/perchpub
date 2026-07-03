# user-account Specification

## Purpose
TBD - created by archiving change add-authed-station-management. Update Purpose after archive.
## Requirements
### Requirement: View and update own profile

A logged-in user SHALL be able to view and update their own profile (`full_name`, `email`) from the authenticated zone, backed by the backend `GET /users/me` and `PATCH /users/me` through the generated typed client in a server-side form action. An attempt to change the email to one already in use SHALL surface the backend's `409` as a field error rather than navigating away. The account page SHALL be reachable only inside the `(app)` zone, behind the P0 server-side auth guard.

#### Scenario: a user updates their full name
- **WHEN** a logged-in user submits the profile form with a new `full_name`
- **THEN** the form action calls `PATCH /users/me`, the profile is updated, and the page reflects the new value

#### Scenario: changing to a taken email is rejected
- **WHEN** a user submits the profile form with an `email` already used by another account
- **THEN** the backend responds `409` and the form re-renders with an "email already in use" field error

#### Scenario: the account page requires authentication
- **WHEN** an unauthenticated client requests the account page in the `(app)` zone
- **THEN** P0's `(app)` guard redirects the request to the login route before the page renders

### Requirement: Change own password

A logged-in user SHALL be able to change their password from the account page by submitting `current_password` and `new_password`, sent to the backend `PATCH /users/me/password` through the generated typed client in a server-side form action. Both fields carry `UpdatePassword`'s `min_length=8`, so a value shorter than 8 characters (current OR new) surfaces as a `422` validation error before the verify step — the form SHALL enforce/echo this so the `400` paths below are reached with well-formed input. Backend rejections — an incorrect current password (`400`) or a new password identical to the current one (`400`) — SHALL be surfaced as field errors.

#### Scenario: a user changes their password
- **WHEN** a user submits a correct current password and a valid, different new password
- **THEN** the form action calls `PATCH /users/me/password` and the page confirms the password was updated

#### Scenario: an incorrect current password is rejected
- **WHEN** a user submits an incorrect current password
- **THEN** the backend responds `400` ("Incorrect password") and the form shows that error without changing the password

#### Scenario: reusing the current password is rejected
- **WHEN** a user submits a new password identical to the current one
- **THEN** the backend responds `400` and the form shows a "new password cannot match the current one" error

### Requirement: Delete own account

A logged-in non-superuser SHALL be able to delete their own account from the account page via the backend `DELETE /users/me` through the generated typed client in a server-side form action, behind a confirmation step. On success the BFF session cookie SHALL be cleared and the user redirected to the public landing. A superuser SHALL NOT be able to self-delete: the backend's `403` SHALL be reflected as an explained, disabled delete control.

#### Scenario: a non-superuser deletes their account
- **WHEN** a logged-in non-superuser confirms account deletion
- **THEN** the form action calls `DELETE /users/me`, the `pp_session` cookie is cleared, and the user is redirected to the public landing

#### Scenario: a superuser cannot self-delete
- **WHEN** a logged-in superuser views the account page
- **THEN** the delete control is disabled and explained, and any attempt is rejected by the backend `403` without deleting the account

### Requirement: Public self-registration (signup)

An anonymous visitor SHALL be able to register a new account from a public-zone signup page by submitting `email`, `password`, and an optional `full_name`, sent to the backend `POST /users/signup` through the generated typed client in a server-side form action. On a successful signup the action SHALL immediately establish a session for the just-registered account by performing the password grant (`POST /login/access-token`) with the just-submitted credentials, setting the `pp_session` cookie (per `web-frontend`'s BFF cookie-session requirement), and SHALL redirect the user into the first-station setup workflow. When the follow-up grant does not succeed — the expected outcome when the email already belongs to an account whose password differs — the action SHALL NOT establish a session and SHALL fall back to the public login form, rendering no account-existence message. This narrows account enumeration **asymmetrically** (an accepted trade-off for a self-hosted / small-multi-tenant deployment): confirming an email is *unregistered* is inseparable from registering it — the signup succeeds and squats the address, self-defeating for probing — whereas an *already-registered* address can still be confirmed side-effect-free, because a probe with an arbitrary password fails the grant and the redirect destination (login form vs. first-station setup) then reveals that the account exists. Fully closing the registered-address oracle is out of scope and deferred to `harden-enrollment-for-multitenancy`. The signup page SHALL live in the `(public)` zone with no auth guard.

#### Scenario: a new visitor is signed in and sent to first-station setup

- **WHEN** an anonymous visitor submits the signup form with an unregistered email and a password
- **THEN** the action creates the account, performs the password grant, sets the `pp_session` cookie, and redirects the user into the first-station setup workflow

#### Scenario: signup for an existing email establishes no session and falls back to login

- **WHEN** the submitted email already belongs to an existing account and the follow-up grant fails
- **THEN** the action does not establish a session and falls back to the login form, rendering no account-existence message

#### Scenario: an authenticated user is redirected away from signup

- **WHEN** an already-logged-in user navigates to the signup page
- **THEN** the page redirects them away from signup into the authenticated zone

