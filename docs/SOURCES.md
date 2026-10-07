# Sources

Checked **2026-10-07**. These notes are why `rules/maryland.yaml` has the numbers it has. If a page and the YAML disagree, the YAML is what the app runs, and the page is what you should re-read. Verify with MVA before you rely on a date.

`https://emissions.mva.maryland.gov/` returned **HTTP 500** on 2026-10-07, so the VEIP rules below are taken from the current MDOT MVA pages that describe VEIP. Older staging copies are cited only where they disagree.

## VEIP testing cycle

Page: [Vehicle Emissions Inspection](https://mva.maryland.gov/title-registration/vehicle-emissions-safety-inspections/vehicle-emissions-inspection)

Checked 2026-10-07. The page says eligible vehicles are generally tested every two years:

- Used vehicles: test every 2 years.
- New vehicles: the first test is 72 months from the model year, then every 2 years. "New" on that page means 2019 or newer, original owner, titled in Maryland, and not previously titled in any other jurisdiction.

The same page lists the counties that require VEIP. Prince George's County is on the list, along with Anne Arundel, Baltimore City, Baltimore, Calvert, Carroll, Cecil, Charles, Frederick, Harford, Howard, Montgomery, Queen Anne's, and Washington.

YAML: `veip.cycle_months` is 24. `veip.new_vehicle.model_year_min` is 2019. `veip.new_vehicle.exempt_months` is 72. `veip.counties` includes Prince George's.

## Notice-to-due-date window

Same emissions page, checked 2026-10-07:

> The MVA will notify you by email 8 weeks before your test is due. If your email address is not on file with the MVA, you will be notified via U.S. mail approximately 6 to 8 weeks before your test due date.

YAML: `veip.notice.email_weeks_before_due` is 8. Mail is `mail_weeks_before_due_min` 6 through `mail_weeks_before_due_max` 8. That span is the notice-to-due window the app shows. It is not the separate 7-day household reminder.

A staging FAQ ([VEIP Frequently Asked Questions](https://stg-mva.maryland.gov/about-mva/Pages/info/58000VEI/58000-07T.aspx)) also mentions a 2-week reminder email. The current public emissions page quoted above does not, so the YAML does not add that second email. An older staging requirements page ([VEIP - General Requirements](https://stg-mva.maryland.gov/about-mva/Pages/info/58000VEI/58000-06T.aspx)) says email notice at 11 weeks. The app follows the current emissions page (8 weeks), not that older line.

## New-vehicle and other exemptions

Two current pages, both checked 2026-10-07, do not use the same words for the 72 months:

- The emissions page says the first test "will occur 72 months from the model year", and the bullet list also says "New vehicles and qualified hybrids for the first 72 months after titling and registration with original ownership".
- [Extensions, exemptions, and waivers](https://mva.maryland.gov/title-registration/vehicle-emissions-safety-inspections/vehicle-emissions-inspection/extensions-exemptions-waivers) says "New vehicles and qualified hybrids for the first 72 months after the model year of the vehicle with original ownership" and, for a lease buyout, "72 months after the model year" for the original lessee.
- The staging FAQ says newly purchased Maryland vehicles with original ownership test "72 months from time of titling/registration", then every two years.

The YAML default anchor is `model_year_start` (January 1 of the model year plus 72 months), because "from the model year" is the schedule sentence on the main emissions page. Change `veip.new_vehicle.anchor` to `title_date` if myMVA shows a title-based date. Qualifying ownership values are `original_maryland` and `lease_buyout_original_lessee`.

Other exemptions copied from those two pages into `veip.exemptions`:

- 1995 or older under 8,500 lb GVWR
- more than 26,000 lb GVWR
- powered solely by diesel, or solely by electric
- motorcycle
- farm truck, farm truck tractor, or farm area vehicle
- historic or antique
- fire apparatus, ambulance, Class N street rod, tactical military vehicle
- Class H school vehicle or Class P passenger bus

The emissions page also says all hybrid vehicles (part gasoline and part electric or propane) are required to be inspected. The YAML flag `hybrids_required_after_new_vehicle_window` records that. A new qualified hybrid still gets the 72-month window; after that it is not exempt.

The emissions page says anyone who buys a used vehicle receives a VEIP notice four months after the registration date. The staging FAQ says three months, and the October 2023 modernization note says a change of ownership is tested two years after purchase. Those disagree. YAML stores `used_purchase_notice_months: 4` from the current emissions page and sets `apply_used_purchase_notice_as_due_date: false`, so the app will not invent a due date from it. Enter the date on the notice.

Modernization background, not used as a second set of numbers: [MVA and MDE implementing modernized VEIP regulations](https://mva.maryland.gov/news/motor-vehicle-administration-department-environment-implementing-modernized-veip-regulations) (regulations effective 2023-10-04; six years for 2019-or-newer original-owner vehicles, then every two years).

## Late fee

Same emissions page, and [Fees and payment options](https://mva.maryland.gov/title-registration/fees-payment-options), both checked 2026-10-07:

- VEIP test fee at a station: $30
- Self-serve kiosk: $26
- Penalty late fee: $30, "assessed the day after the due date and every four weeks (28 days) thereafter"

YAML: `late_fee.amount_usd` 30, `repeat_every_days` 28, station fee 30, kiosk fee 26. The first charge is on the day after the due date. Each 28 days after that day adds another charge. Completing the test by an extended due date avoids the late fee; that sentence is on the [extensions page](https://mva.maryland.gov/title-registration/vehicle-emissions-safety-inspections/vehicle-emissions-inspection/extensions-exemptions-waivers).

## Registration period

Two current pages, both checked 2026-10-07, do not say the same thing:

- [Title and registration](https://mva.maryland.gov/title-registration): "Registration must be renewed every one or two years".
- [Renew registration](https://mva.maryland.gov/title-registration/renew-registration): "Registrations are available for a one-, two-, or three-year period."

YAML: `registration.periods_years` is 1 and 2, matching the overview and the request this app was built for. `also_offered_years` includes 3 because the renew page offers it. The default period is 2.

[COMAR 11.15.16.05](https://regs.maryland.gov/us/md/exec/comar/11.15.16.05) says a staggered registration period shall not exceed 3 years unless the Administration approves otherwise, and "Registration renewals shall be due on or before the last day of the month stated on the registration card."

[COMAR 11.15.16.03](https://regs.maryland.gov/us/md/exec/comar/11.15.16.03) says the registration expires at midnight on the expiration date indicated on the card.

YAML `planning_deadline` is `card_date`: reminders use the date you type from the card. The app also shows the last day of that month so the COMAR month-end line is visible. You can switch `planning_deadline` to `last_day_of_month_on_card` if you want reminders to use that day instead.

## Registration notice timing

[Renew registration](https://mva.maryland.gov/title-registration/renew-registration), checked 2026-10-07:

- "The MVA will send you a renewal notice when it's time."
- "You may renew 90 days before your expiration date."

The page does not say the notice is mailed a fixed number of days or weeks ahead. YAML `registration.notice.published_lead_time_days` is null on purpose. The dated rule the app can count is the 90-day early-renewal opening (`early_renew_days_before_expiration`).

Two related timings are stored so they are not mistaken for a notice lead time:

- Mail processing: older MVA renewal instructions say that if you renew by mail, the notice must be received at the MVA no later than 15 days before expiration. That line is still on the staging copy [Renewing Your Vehicle Registration](https://stg-mva.maryland.gov/vehicles/Pages/registration/renew.aspx) and in circulating VR-004 instruction sheets. The current renew page does not repeat it. YAML `mail_must_arrive_days_before_expiration` is 15, labeled as that mail deadline.
- Flags, not the renewal notice: [Remove vehicle flags](https://mva.maryland.gov/title-registration/remove-vehicle-flags) says the MVA emails about 30 days after a flag is placed and 70 days before registration expires. YAML `flag_email_days_before_expiration` is 70.

Household reminders inside the app are still the configurable 7-day window (and overdue), measured from the registration expiration you entered. The 90-day, 15-day, and 70-day figures are shown as MVA timing context.
