## ADDED Requirements

### Requirement: First-station onboarding on the dashboard

The authenticated dashboard SHALL be onboarding-aware: its server `load` SHALL determine how many stations the current user owns, and when the user owns **zero** stations the dashboard SHALL lead with a prominent "set up your first station" call to action that routes to the station-setup wizard. When the user owns **one or more** stations the dashboard SHALL NOT show that onboarding call to action. This onboarding recommendation SHALL be the standing post-signup next step until the user owns at least one station.

#### Scenario: a user with no stations sees the setup call to action

- **WHEN** a logged-in user who owns zero stations loads the dashboard
- **THEN** the dashboard leads with a prominent "set up your first station" action that links to the station-setup wizard

#### Scenario: a user with a station sees the normal dashboard

- **WHEN** a logged-in user who owns at least one station loads the dashboard
- **THEN** the dashboard does not show the first-station onboarding call to action

### Requirement: Station setup is not a top-level navigation destination

The authenticated app shell's primary navigation SHALL NOT present station setup / device enrollment as a standalone top-level destination. Station setup SHALL be reached from the dashboard's first-station onboarding call to action and from the station list's secondary "Add station" action (see `station-management`). The primary navigation SHALL retain Dashboard, the station list ("My stations"), and Account (plus the superuser Admin section).

#### Scenario: the sidebar has no standalone enroll destination

- **WHEN** a logged-in user views the authenticated app shell
- **THEN** the primary navigation shows Dashboard, My stations, and Account, and shows no standalone "Enroll device" navigation item

#### Scenario: station setup remains reachable without a nav item

- **WHEN** a logged-in user wants to set up a station
- **THEN** they can reach the station-setup wizard from the dashboard onboarding call to action or the station list's "Add station" action

### Requirement: The station-setup wizard offers a defer-to-later escape

The station-setup wizard SHALL provide a "do it later" escape that leaves setup and returns the user to the dashboard, where the first-station onboarding call to action continues to recommend setup until a station exists. Deferring SHALL NOT create a station and SHALL NOT prevent later setup.

#### Scenario: a user defers first-station setup

- **WHEN** a logged-in user who owns no stations opens the setup wizard and chooses "do it later"
- **THEN** no station is created, the user is returned to the dashboard, and the dashboard still shows the first-station onboarding call to action
