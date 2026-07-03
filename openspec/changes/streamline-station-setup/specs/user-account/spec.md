## MODIFIED Requirements

### Requirement: Public self-registration (signup)

An anonymous visitor SHALL be able to register a new account from a public-zone signup page by submitting `email`, `password`, and an optional `full_name`, sent to the backend `POST /users/signup` through the generated typed client in a server-side form action. On a successful signup the action SHALL immediately establish a session for the just-registered account by performing the password grant (`POST /login/access-token`) with the just-submitted credentials, setting the `pp_session` cookie (per `web-frontend`'s BFF cookie-session requirement), and SHALL redirect the user into the first-station setup workflow. When the follow-up grant does not succeed — the expected outcome when the email already belongs to an account whose password differs — the action SHALL fall back to the public login form without asserting whether an account already exists, preserving the backend's account-non-enumeration guarantee (positive confirmation that an email was unregistered is inseparable from having just registered it; an existing email is indistinguishable from a mistyped password). The signup page SHALL live in the `(public)` zone with no auth guard.

#### Scenario: a new visitor is signed in and sent to first-station setup

- **WHEN** an anonymous visitor submits the signup form with an unregistered email and a password
- **THEN** the action creates the account, performs the password grant, sets the `pp_session` cookie, and redirects the user into the first-station setup workflow

#### Scenario: signup for an existing email falls back to login without enumeration

- **WHEN** the submitted email already belongs to an existing account and the follow-up grant fails
- **THEN** the action does not establish a session, falls back to the login form, and reveals nothing about whether the account already existed

#### Scenario: an authenticated user is redirected away from signup

- **WHEN** an already-logged-in user navigates to the signup page
- **THEN** the page redirects them away from signup into the authenticated zone
