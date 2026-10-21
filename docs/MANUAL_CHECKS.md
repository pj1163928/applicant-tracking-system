# Manual browser checks

Some behavior lives in the browser, where the test suite can't reach it. The
PRD rules out browser automation for these, so they are checked by hand. Run
each list after any change to the code it covers, and note in the PROMPTS.md
entry that you followed it.

## Setup

    uv run python manage.py migrate
    uv run python manage.py seed        # demo data; every user's password is demo-pass-123
    uv run python manage.py tailwind runserver

Open http://127.0.0.1:8000/ and sign in. The checks use the seeded
**Backend Developer** board (Openings → Backend Developer → Pipeline board).
Its designated authority is `manager` (Morgan Patel, a Hiring Manager).

Moves change the database. To start again from the seeded board, delete
`db.sqlite3`, then run `migrate` and `seed`.

## Drag-and-drop on the pipeline board

Covers the board's script in `applications/templates/applications/board.html`,
the card's drop form (`partials/card.html`) and the drag styles in
`assets/css/source.css`. Use a desktop browser with a mouse, then repeat the
touch checks on a phone (or in DevTools device mode with touch turned on).

Sign in as `manager`.

- [ ] **Layout.** The six pipeline stages fill the page with an arrow between
      each: three a row on a wide window, with a connector from Interview down to
      Final Review. Rejected and Withdrawn sit apart under "Out of the pipeline",
      collapsed to counts. Nothing scrolls sideways. Narrow the window to phone
      width: the stages stack with ↓ arrows, and still nothing scrolls sideways.
- [ ] **Hover.** Point at a card without clicking. It lifts slightly and its
      shadow deepens.
- [ ] **Pick up.** Press on the Applied card and move the mouse. The card lifts
      out (slightly tilted, with a deep shadow) and travels with the cursor, solid
      and easy to read. A dashed empty slot stays where it was.
- [ ] **Highlights.** While carrying it: Screening has a green dashed outline;
      Interview, Final Review, Offer, Rejected and Withdrawn have amber ones; Hired
      is faded grey. Applied itself is unmarked. There is no text inside any
      column.
- [ ] **Hovered stage.** Move over Screening. It grows a little, its outline
      becomes a solid green ring with a green tint, and a card-shaped dashed gap
      opens at the bottom of its list. Over an amber stage, the ring, tint and gap
      are amber. Over Hired, it gets a red ring, no gap opens, and the cursor shows
      "not allowed".
- [ ] **Confirm, cancelled.** Release over Screening. The card settles into the
      gap with a dashed blue outline, and a dialog says "You dropped … on
      Screening. This moves them one step forward, from Applied to Screening.",
      with **Move to Screening** focused. Click **Cancel** (or press Escape). The
      card slides back into its slot in Applied and nothing was written.
- [ ] **Confirm, made.** Drop it on Screening again and click **Move to
      Screening** (or press Enter). The card lands in Screening with a brief green
      glow, "Moved … from Applied to Screening." appears above the board, and only
      the two counts change. The page doesn't reload: the Network tab shows two
      POSTs to `/applications/<pk>/move/` (the drop, then the confirmation).
- [ ] **Own column.** Drag a card and drop it back on its own column. It flies
      back into its slot, nothing else happens, and no request is sent.
- [ ] **Links.** Start a drag on a candidate's name and drop it back at home:
      the candidate's page doesn't open. A plain click on the name still opens it.
- [ ] **Needs a note, cancelled.** Drag the Interview card onto Applied. The
      note dialog opens ("This moves … back. Say why."). Click **Cancel**. The
      card is still in Interview, and its history has no new row.
- [ ] **Needs a note, made.** Drag it onto Applied again, type a note and click
      **Move to Applied**. The dialog closes, the card is in Applied, and its
      history shows the note.
- [ ] **Optional note on a collapsed column.** Drag a card onto the collapsed
      **Rejected** panel. The panel lights up (no gap, since it's collapsed) and
      the card shrinks into it. A dialog asks for an optional note. Submit it
      empty. The Rejected count goes up and the panel stays collapsed.
- [ ] **Illegal drop.** Drag the Final Review card onto the faded Hired column
      and drop it. The card flies back into Final Review and gives a small shake,
      and the red message "… can only be moved to Hired from Offer." appears. No
      dialog opens.
- [ ] **Reopen.** Expand Withdrawn and drag its card onto Rejected: refused
      with "A withdrawn application can only be reopened to an active stage, not
      Rejected." Then drag it onto Screening. The note dialog asks why it's being
      reopened.
- [ ] **Escape.** Start a drag and press Escape before dropping. The card flies
      home, every highlight clears and nothing moves.
- [ ] **Edge scrolling.** Make the window short, then carry a card towards the
      bottom edge. The page scrolls down so you can reach Rejected and Withdrawn.
- [ ] **Move menu.** Every card's **Move** menu still works as before: a
      one-step move from the menu happens at once, with no confirmation.
- [ ] **Reduced motion.** Turn on "reduce motion" in the operating system
      (Windows: Settings → Accessibility → Visual effects → Animation effects
      off) and reload. Dragging still lights up the stages and the card still
      follows the pointer, but nothing tilts, grows, slides, glows or shakes.
- [ ] **Dark theme.** Switch to dark with the moon toggle and repeat
      "Highlights" and "Hovered stage": the outlines, rings and faded columns are
      still easy to see.

On a phone, or in DevTools device mode with touch, still as `manager`:

- [ ] **Press and hold.** Hold a finger on a card for a moment. It lifts (a
      short vibration on phones that support it) and then follows your finger.
      The page doesn't scroll while you carry it, and no browser menu opens.
- [ ] **Scroll, not drag.** Swipe quickly up or down starting on a card. The
      page scrolls and nothing is picked up.
- [ ] **Drop by touch.** Carry a card to the next stage and lift your finger.
      The confirmation dialog appears, as with a mouse.

Busy and empty stages, still as `manager`. To crowd a stage, record a few more
applications for Backend Developer (any candidates, any active source); they all
start at Applied.

- [ ] **Newest first.** The most recently recorded or moved card is at the top of
      its stage.
- [ ] **Folding.** With more than three cards, Applied shows only the newest three
      and a "+N more · Show all" button. With three or fewer there's no button.
- [ ] **Expanding and searching.** Click "Show all": every card appears, with a
      search box at the top. Type part of a name: only matching cards stay.
      Type something nobody matches: "No one at Applied matches that name."
      appears. Click "Show fewer": back to three cards, and the search is cleared.
- [ ] **Moves keep the view.** Expand Applied, then drag one of its cards to
      Screening and confirm. Applied stays expanded, its count and button update,
      and the moved card is at the top of Screening.
- [ ] **Empty stages.** A stage with no one shows an inbox icon and "No one at …".
      On a wide window its box is as tall as the other stages in its row, but no
      taller than about three cards. Dragging a card over it replaces the box
      with the gap.
- [ ] **Fresh styles.** In VS Code's Simple Browser and in another browser, the
      page source links `tailwind.css?v=…`, and after `tailwind runserver`
      rebuilds (save a template), a reload shows the change in both.

Sign in as `recruiter` (not this opening's authority).

- [ ] Drag the Final Review card. Offer and Hired are faded. Drop it on Offer:
      refused with "Only Admins, Hiring Managers or Morgan Patel, this opening's
      designated authority, can move applicants into Offer.", and the card stays.

Sign in as `interviewer`.

- [ ] No card can be dragged (no grip dots, and the pointer doesn't change to a
      hand). The board says the role can't move applicants.
