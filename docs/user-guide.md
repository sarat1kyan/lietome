# User guide

## Setting up the room

* Face the person to the camera, at roughly eye level, about an arm's length away. Their face
  should fill about a third of the frame width.
* Light on the face, not behind it. A window behind the person turns the face into a silhouette.
* Keep the camera still. Laptop on a table, not on a lap.
* A quiet room and a microphone near the person help every voice measure.

The live view shows a red banner when something is off: face too small, too dark, blurry,
turned away, low frame rate, or a microphone that hears nothing.

## Consent

Before any session, Lightman asks you to confirm:

* who agreed: the client, a legal guardian, or yourself;
* how: verbally, in writing, electronically;
* to what: analysis of face and posture (required), analysis of voice, a transcript, a video
  recording;
* your initials, and an optional note.

The microphone, the transcript and the recording only run when they are in the agreed scope.
The record is stored with the session and shown in its report.

### Explaining Lightman to a client

> "This program looks at how your face, voice and posture move during our conversation and
> compares them with how you were at the start. It does not know what you feel or think, it does
> not diagnose anything, and it is not a lie detector. Everything stays on this computer. You can
> ask me to stop at any time, and to see or delete what it recorded."

## Calibration

The first 40 seconds set the person's baseline:

1. **Sit** (12 s): sit normally, look at the screen, do not talk.
2. **Read** (14 s): read the passage on screen aloud at a normal pace.
3. **Talk** (14 s): talk freely about something neutral, for example the day so far.

Everything afterwards is measured against this. A rushed or unusual calibration makes every
later number less useful; start again if the person was not settled.

## During the session

The video shows, from the top left: session time and status, the expression pattern meter
(how close the face is to each pattern, with the person's own threshold marked), the signal
tape, and at the right the Action Units with their names and how far each is from baseline.
The circle at the bottom right is expressed affect: right is more positive, up is more
activated, both compared with calibration.

Write notes as you go (the note field in the live panel); they are pinned to the moment and
appear on the timeline.

**A second screen for the client**: open the same address with `#subject` at the end on
another device or window. It shows only the reading passage and the questions.

## Reading a session

### Overview

* **Valence and arousal**: the averages after calibration and the share of time the face and
  voice looked more positive, more negative, more activated or calmer than at the start. The
  chart shows how this moved; click it to jump to the moment.
* **Oriented to the conversation**: the share of time the face and gaze were turned to you. Use
  it as a trend for one person, not as a score.
* **Talk time**: how much of the speech was the client's (mouth moving) and how much was
  someone else's, and how many turns each had.
* **Summary**: the same in plain sentences, with the caveat that applies to each measure.
* **Key moments**: the largest changes spread across the session, with thumbnails.

### Review

The timeline shows every signal in units of this person's own spread (SD): 0 is their
calibration level, the dashed lines are 3 SD. The event strip above it holds episodes,
expression patterns, gestures, gaze-away periods and voice events. Click anything to see what
was measured, what it does not mean, and what to check.

Keyboard: arrows move 1 s (with shift 5 s), j and k jump to the next and previous event, c
compares two stretches you drag on the timeline.

### Conversation

The transcript highlights hedges ("I think", "to be honest") in amber and denials ("no", "I
didn't") in red. Denials that came with a face or body change within a second are listed
underneath. Answers to marked questions appear in the question table.

## Clients and trends

The Clients page lists every code with its sessions. Click a code to see one sparkline per
measure across that client's sessions. Trends mean most when sessions were recorded in similar
conditions (same room, light and camera).

**Export** downloads everything about a client as a zip. **Erase** deletes their sessions,
notes, norms and entry after you type the code to confirm; it cannot be undone.

## Reports

**Report** on a session opens a single HTML file with the overview, notes, key moments and the
consent record. It contains face images: share it only with the person it shows.

## Profiles

* **Practice** (default): affect, engagement, talk time, notes, trends. Deception-research
  material is hidden everywhere, including reports.
* **Research**: adds the deception-research cue checklist, the possibility index per answer,
  the blind validation card game, and raw signal views. Every such number comes with its
  effect size and the caveat that it is not a probability.

Change the profile in Settings.

## Research profile

### Interview protocol

In the live view, open **protocol** and write questions one per line: `C:` control, `R:`
relevant, `N:` neutral, optionally followed by `[truth]` or `[lie]` as the expected class.
Press **ask next** (or `n`) as you read each question aloud and **end answer** when the
person stops. The session gets a table per question: response latency, speech time, changes
per minute, strongest signals, blink rate and pitch shift, a control against relevant
comparison with a permutation p-value, and an AUROC when expected classes were given. No
answer is ever labelled a lie.

### Validation game

The card game hands the person a hidden truth or lie card per question on their own screen.
After the session the scores are compared with the cards, with bootstrap intervals, per session
and pooled per person. This tells you how well the measures work for this person in this room,
which is usually: not much better than chance.

## Command line

```bash
lightman serve [-o FOLDER] [--host 0.0.0.0]   # web interface
lightman analyze clip.mp4 --subject C-014     # recording, analysed offline
lightman live [--au] [--source clip.mp4]      # preview window without the browser
lightman report SESSION_FOLDER                # standalone HTML report
lightman setup | bench | models list | models download NAME
```

`lightman --help` and `lightman COMMAND --help` list every option. Sessions analysed from the
command line note that consent was not recorded in Lightman; keep your own record.
