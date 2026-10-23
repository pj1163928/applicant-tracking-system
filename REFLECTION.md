## 1a. ModelForm, aka CandidateForm

**Location:** `CandidateForm` in `candidates/forms.py` inherits from `forms.ModelForm`. It is used in `candidates/views.py:84–99`.

**Purpose:** This form is used to add/edit the contact details of a candidate, like first name, last name, email, phone, and other notes.

**Functionality:** `CandidateCreateView` and `CandidateUpdateView` in `candidates/views.py` also use the form to validate user input and commit the changes to the database. The `candidate_form.html` template is the one that actually renders the form fields, errors, and helpful text information.

As this is a `ModelForm`, Django will automatically build the fields and validation rules from the `Candidate` model. `form.save()` creates or updates the database record.

## 1b. ChangeAuthorityForm, or the plain Form

**Location:** `OpeningAuthorityView` in `openings/views.py:538–578` uses this form.

**Purpose:** This form is utilized by admins or recruiters to choose new designated authorities for job openings and optionally provide the reason for the change.

**Functionality:** Unlike `CandidateForm`, the form class explicitly declares its fields. `OpeningAuthorityView` verifies and validates the submitted information and passes it to `change_authority()`, a service routine. This, in turn, updates the authority, logs the change in the event history, and sends the notification. Lastly, the `jobopening_authority.html` template displays the form fields, including the new designated authority.

## 1c. Differences

The main difference between the two forms is that the `ModelForm` is connected directly to a database model. It automatically generates fields and provides model-based validation. It also has the ability to save changes using `form.save()`.

A regular `Form` defines its fields manually and will not automatically save to a model. In my application, the purpose of `CandidateForm` is a straightforward database operation, whereas `ChangeAuthorityForm` relies on more complex rules, such as business rules, recording history, and sending notifications.

## 2. Many-to-Many Relationship – Job Openings and Skills

One of the many-to-many (M2M) relationships that I have in my codebase revolves around job openings and skills. This uses the `JobOpening`, `Skill`, and `JobOpening.skills` models.

- **JobOpening:** The posted opening.
- **Skill:** A named skill.
- **JobOpening.skills:** A declaration at `openings/models.py:232`.

A single foreign key would not suffice in this relationship, as each side needs to point to many others on the opposing side. An opening may need many skills, and likewise, a skill may be wanted for many openings.

If a key were placed on either side, it would limit us to one row, and other options, such as a comma-separated field, would cause issues with querying or being constrained. Additionally, it would create duplicate rows, making the idea that it is just a singular skill problematic.

Django also did not create this association automatically. It was explicitly defined so that an opening points to several skills and a skill points to several openings.

The model is also an explicit association model, which takes advantage of a few key features:

- **Unique:** Can't make duplicate pairs.
- **PROTECT:** The skill cannot be removed.
- **Attach and Detach:** This allows a skill to be retired and reused.

The table only holds the link, with no extra columns except for its ID and keys. The relationship also contains business rules.

## 3. Prototyping

I went through four prototyping sessions with Claude. One of them was with the pipeline board, as I honestly did not know what Claude was considering for my design.

Claude and I had earlier settled on how to view permissions and views. But overall, it made it harder for me to understand what the board would look like. I did go with the base model of the board but made quite a few tweaks, such as animations and styling, as well as how advancements in the board should work and whether to view withdrawn or rejected applications.

**Source:** `PROMPTS.md:1061`

Some functionality I decided on was that drag-and-drop should be implemented. Later on, I made some additional changes to the board's appearance and also added editing confirmation to make sure that edits were not made accidentally.

## 4. Design Defence

One of the decisions that I made was around grace periods. Claude did not suggest this, and it essentially was prompted around how we should handle applicants when a position is closed, whether automatically or manually.

This added a newer level of complexity, but it also made sure that candidates were being treated fairly.

Each candidate would be given a chance, along with additional days and reasoning. It also gave the hiring managers greater flexibility to extend a candidate's hiring cycle in case something went wrong.

Claude opted for a simpler approach, or just outright cancelling applications. I felt there could be more flexibility.

**Source:** `PROMPTS.md:1066–1068`

Disclosure: AI was used for the readability of this markdown document, all thoughts are hman generated.