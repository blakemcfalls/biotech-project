#!/usr/bin/env python3
"""
LanM Phase 1 daily dashboard.

One command:  python3 dashboard.py
Then open:    http://localhost:8787

Stdlib only. No database, no framework, no build step.

Files beside this one:
  plan.json  full task plan, seeded once then mutated by check-ins
  log.json   append-only record of each night's check-in

Both stay hand-editable. Edit either in a text editor and reload the page;
missing fields are filled with defaults rather than crashing.

Flags:
  --today YYYY-MM-DD   pretend it is this date (also honours ?date= in the URL)
  --seed               rewrite plan.json and log.json from the seed, then exit
  --port N             listen on another port (default 8787)
  --host H             bind address (default 0.0.0.0, so a phone on the LAN can reach it)
"""

import argparse
import html
import json
import math
import os
import sys
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_PATH = os.path.join(HERE, "plan.json")
LOG_PATH = os.path.join(HERE, "log.json")

EVENING_HOUR = 17  # before this, the morning view is the default


# --------------------------------------------------------------------------
# date helpers
# --------------------------------------------------------------------------

def pd(s):
    """Parse an ISO date. Tolerant of None and of stray whitespace."""
    if not s:
        return None
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s).strip())


def ds(d):
    return d.isoformat() if d else None


def human(d):
    return d.strftime("%a %b %-d") if hasattr(d, "strftime") else str(d)


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


# --------------------------------------------------------------------------
# seed data, derived from "LanM Phase 1 - Procedure & Timeline (Nov 9 - Dec 14, 2026)"
# --------------------------------------------------------------------------

def seed_plan():
    T = []

    def task(tid, week, d, title, detail, mins, loc, blocked_by=None,
             critical=False, why="", lag_days=0, active=True):
        T.append({
            "id": tid,
            "week": week,
            "scheduled_date": d,
            "title": title,
            "detail": detail,
            "duration_min": mins,
            "location": loc,
            "blocked_by": blocked_by or [],
            "status": "pending",
            "completed_date": None,
            "notes": "",
            "critical": critical,
            "why": why,
            "lag_days": lag_days,
            "active": active,
        })

    # ---- Week 0: Nov 9-15, approvals and ordering -------------------------
    task("w0-spec", 0, "2026-11-09",
         "Write one-page construct specification",
         "Host strain, vector backbone, promoter, tag, resistance marker, and the "
         "three inserts.", 90, "anywhere")
    task("w0-rdna-note", 0, "2026-11-09",
         "Note K-12 host, frame BSL-1 rDNA vs BSL-2",
         "Record that the host is a laboratory K-12 derivative and the work is "
         "recombinant DNA, so the question put to review is BSL-1 rDNA versus BSL-2.",
         30, "anywhere")
    task("w0-containment", 0, "2026-11-09",
         "Draft containment and decontamination section",
         "List segregation of transformed and untransformed cultures.",
         60, "anywhere")

    task("w0-supervisor", 0, "2026-11-10",
         "Meet supervisor, request written determination",
         "Present the construct specification and ask for a written biosafety level "
         "determination. Confirm which approval forms the fair requires and who signs "
         "them. Confirm the school holds a lab at the determined level and that "
         "supervision is available on the days the procedure needs it. Agree the date "
         "by which approval will be signed.",
         60, "anywhere", ["w0-spec"])
    task("w0-order-genes", 0, "2026-11-10",
         "Order three genes, cloned into expression vector",
         "Order three genes each cloned into an expression vector, not as linear "
         "fragments. T7/lac promoter, N-terminal His-tag, resistance marker.",
         60, "anywhere", ["w0-supervisor"], critical=True,
         why="Gene synthesis is the one step that cannot be repeated inside the window.")
    task("w0-price-tiers", 0, "2026-11-10",
         "Price express against standard tier",
         "Price the express synthesis tier against the standard tier and record both "
         "delivery estimates.", 20, "anywhere")

    task("w0-shipping", 0, "2026-11-11",
         "Confirm shipping to school address",
         "Confirm the supplier will ship to the school address, and whether an "
         "institutional account is required.", 20, "anywhere")
    task("w0-order-reagents", 0, "2026-11-11",
         "Place the full reagent order",
         "Competent cells, LB broth and agar, antibiotic, IPTG, lysozyme, Ni-NTA "
         "columns and buffers, NdCl3, CaCl2, native PAGE gels and buffer, stain, "
         "ladder, consumables.", 60, "anywhere", ["w0-supervisor"])

    task("w0-protocol", 0, "2026-11-12",
         "Revise protocol to Phase 1 scope and submit",
         "Revise the protocol document to the Phase 1 scope and submit it alongside "
         "the approval forms.", 120, "anywhere")

    task("w0-book-lab", 0, "2026-11-13",
         "Book lab access and supervisor for weeks 1, 3, 4",
         "Book lab access and supervisor availability for weeks 1, 3 and 4.",
         30, "anywhere")
    task("w0-freezer", 0, "2026-11-13",
         "Confirm freezer availability and freezing method",
         "Confirm freezer availability and which freezing method week 3 will use.",
         20, "anywhere")

    task("w0-determination", 0, "2026-11-14",
         "Signed biosafety determination in hand",
         "The written determination, signed. Nothing is ordered until the biosafety "
         "classification is on paper.",
         15, "anywhere", ["w0-supervisor"], critical=True,
         why="This is the only annotation that can remove the December deliverable entirely.")
    task("w0-gel-plan", 0, "2026-11-14",
         "Write the gel loading plan",
         "Lanes, conditions, ladder position, and which lanes carry the controls.",
         60, "anywhere")

    # ---- Week 1: Nov 16-22, transformation and stocks ---------------------
    task("w1-dna-received", 1, "2026-11-17",
         "DNA received",
         "Placeholder date until the supplier's estimate is recorded (fork F2) and "
         "the actual arrival is logged (fork F4).",
         15, "anywhere", ["w0-order-genes"], critical=True,
         why="Gate at Nov 23 if DNA has not arrived.", lag_days=4)
    task("w1-log-receipt", 1, "2026-11-17",
         "Log receipt, check map and sequence, store at -20",
         "Log receipt, check the construct map and sequence file against what was "
         "ordered, and store the DNA at -20 C.",
         30, "anywhere", ["w1-dna-received"])
    task("w1-confirm-super", 1, "2026-11-17",
         "Confirm supervisor present for transformation",
         "Confirm the supervisor is present for the transformation session.",
         15, "anywhere")

    task("w1-transform", 1, "2026-11-18",
         "Transformation session",
         "Thaw chemically competent cells on ice and keep them on ice throughout. Add "
         "plasmid DNA to each aliquot; incubate on ice 30 minutes. Heat-shock at 42 C "
         "for 30 seconds, then return to ice for 5 minutes. Add recovery medium; shake "
         "at 37 C for 1 hour. Plate onto LB agar with the selection antibiotic, one "
         "plate per variant. Plate two controls: untransformed cells on antibiotic, "
         "which must show no growth, and untransformed cells on plain LB, which must "
         "grow. Incubate overnight at 37 C.",
         180, "lab", ["w1-log-receipt"])

    task("w1-read-plates", 1, "2026-11-19",
         "Read plates, check the negative control",
         "Colonies on the variant plates and none on the negative control plate means "
         "selection worked.", 30, "lab", ["w1-transform"], lag_days=1)
    task("w1-pick-colonies", 1, "2026-11-19",
         "Pick two colonies per variant into liquid culture",
         "Pick two well-separated colonies per variant into liquid culture with "
         "antibiotic; grow overnight with shaking at 37 C.",
         45, "lab", ["w1-read-plates"])

    task("w1-glycerol", 1, "2026-11-20",
         "Make and freeze glycerol stocks",
         "Make glycerol stocks from each overnight culture and freeze them.",
         60, "lab", ["w1-pick-colonies"], critical=True,
         why="This is the checkpoint that protects the rest of the schedule.",
         lag_days=1)
    task("w1-autoclave", 1, "2026-11-20",
         "Autoclave plates and spent culture",
         "Autoclave all plates and spent culture before disposal.",
         30, "lab", ["w1-read-plates"])

    task("w1-retransform", 1, "2026-11-20",
         "Repeat transformation",
         "One repeat transformation fits in this week if no colonies appear. A second "
         "failure means the fallback decision moves forward to Nov 23.",
         180, "lab", [], active=False)

    # ---- Week 2: Nov 23-29, Thanksgiving, low intensity --------------------
    task("w2-test-expr", 2, "2026-11-23",
         "Small-scale test expression",
         "One culture per variant, induce with IPTG, take samples before induction and "
         "after 3 hours at 37 C.",
         240, "lab", ["w1-glycerol"], active=False)
    task("w2-test-gel", 2, "2026-11-24",
         "Denaturing gel on test expression samples",
         "Run those samples on a denaturing gel to confirm a band appears at the "
         "expected size.", 180, "lab", ["w2-test-expr"], active=False)
    task("w2-record", 2, "2026-11-24",
         "Record the test expression result",
         "A visible induced band here removes most of the risk from week 3.",
         20, "anywhere", ["w2-test-gel"], active=False)

    task("w2-buffers", 2, "2026-11-23",
         "Prepare and label the five buffers",
         "Lysis, binding, wash, elution, native running buffer. Stable at room "
         "temperature or 4 C.", 120, "anywhere")
    task("w2-metal-stocks", 2, "2026-11-24",
         "Prepare Nd3+ and Ca2+ stock solutions",
         "Prepare the Nd3+ and Ca2+ stock solutions, with goggles on, and label "
         "concentrations clearly.", 60, "anywhere")
    task("w2-imagej", 2, "2026-11-25",
         "Write and test the ImageJ quantification procedure",
         "Write the ImageJ quantification procedure and test it on a practice gel "
         "image so the method is settled before real data exists.", 120, "anywhere")

    task("w2-draft", 2, "2026-11-27",
         "Draft results and methods, figures blank",
         "Draft the results and methods sections of the write-up with the figures left "
         "blank.", 180, "anywhere")
    task("w2-phase2", 2, "2026-11-28",
         "Prepare the Phase 2 outline",
         "Prepare the Phase 2 outline so it is ready regardless of how Phase 1 lands.",
         120, "anywhere")

    # ---- Week 3: Nov 30 - Dec 6, expression, lysis, purification -----------
    task("w3-overnight", 3, "2026-11-30",
         "Inoculate overnight cultures from glycerol stocks",
         "Inoculate from glycerol stocks into LB with antibiotic; grow overnight with "
         "shaking at 37 C.", 45, "lab", ["w1-glycerol"])
    task("w3-expression", 3, "2026-12-01",
         "Grow to mid-log, induce, harvest, freeze pellets",
         "Dilute each overnight culture into fresh LB with antibiotic and grow at 37 C "
         "to mid-log density. Take a 1 mL pre-induction sample from each and keep it "
         "for the gel. Add IPTG to induce; continue shaking at 37 C for 3 hours. Take a "
         "post-induction sample from each. Harvest cells by centrifugation; discard the "
         "supernatant into disinfectant; freeze the pellets.",
         300, "lab", ["w3-overnight"], lag_days=1)
    task("w3-lysis", 3, "2026-12-02",
         "Lysozyme pre-incubation and three freeze-thaw cycles",
         "Resuspend each pellet in lysis buffer containing lysozyme. Incubate on ice 30 "
         "minutes to weaken the cell walls before the first freeze. Freeze: -80 C for 15 "
         "minutes per cycle preferred; dry ice and ethanol for about 5 minutes is an "
         "equivalent fast freeze; -20 C works but needs at least 1 hour per cycle. Thaw "
         "in a 37 C water bath until just liquid. Three cycles total. Centrifuge and keep "
         "the supernatant. Keep a small sample of the pellet for the gel, so an insoluble "
         "result is diagnosable rather than invisible.",
         240, "lab", ["w3-expression"])
    task("w3-nickel", 3, "2026-12-03",
         "Ni-NTA purification, keep every fraction",
         "Equilibrate the Ni-NTA column with binding buffer. Load the supernatant and "
         "collect the flow-through. Wash and collect the wash. Elute in small fractions, "
         "collecting each separately. Keep every fraction: if the elution is empty, the "
         "flow-through and wash tell you where the protein went.",
         180, "lab", ["w3-lysis"])
    task("w3-confirm-gel", 3, "2026-12-04",
         "Denaturing gel, confirm enriched elution band",
         "Run a denaturing gel with pre-induction, post-induction, soluble lysate, "
         "insoluble pellet, flow-through, wash, and elution fractions. Stain, image, and "
         "confirm a band at the expected size that is enriched in the elution lanes.",
         240, "lab", ["w3-nickel"], critical=True,
         why="Without this, week 4 has nothing to assay - this is the second gate.")
    task("w3-conc", 3, "2026-12-04",
         "Estimate concentration, buffer-exchange if needed",
         "Estimate concentration, and buffer-exchange or dilute into the assay buffer if "
         "the elution buffer would interfere with the native gel.",
         60, "lab", ["w3-confirm-gel"])

    # ---- Week 4: Dec 7-13, assay, quantification, write-up -----------------
    task("w4-assay-1", 4, "2026-12-07",
         "First assay run, six samples",
         "Two variants x three conditions: protein only, protein with Nd3+, protein with "
         "Nd3+ plus a large Ca2+ excess. Keep protein concentration identical across all "
         "six - differences in loading look exactly like differences in dimerization. "
         "Incubate 30 minutes at room temperature. Load onto a native, non-denaturing gel "
         "alongside a native ladder; record the lane order before running. Run cold or in "
         "short bursts if the rig warms. Stain with Coomassie, destain, and image on a "
         "flat, evenly lit background.",
         300, "lab", ["w3-confirm-gel"])
    task("w4-assay-23", 4, "2026-12-08",
         "Replicate runs two and three",
         "Repeat the full six-sample layout twice more from the same purified protein. "
         "Image each gel under identical conditions so band intensities are comparable.",
         360, "lab", ["w4-assay-1"])
    task("w4-quant", 4, "2026-12-09",
         "ImageJ quantification, tabulate replicates",
         "Measure monomer and dimer band intensity per lane in ImageJ, subtracting local "
         "background. Compute the dimerization metric. Tabulate all replicates; do not "
         "average away a replicate that disagrees.",
         240, "anywhere", ["w4-assay-23"])
    task("w4-spare", 4, "2026-12-10",
         "Spare day: repeat run or R100A assay",
         "Held for a repeat run if a gel failed, or for an R100A assay if that variant "
         "purified successfully.", 300, "lab", [])
    task("w4-figure", 4, "2026-12-11",
         "Produce the dimerization figure",
         "Dimerization fraction by variant and condition, with individual replicate "
         "points shown.", 180, "anywhere", ["w4-quant"])
    task("w4-writeup", 4, "2026-12-11",
         "Write results and interpretation",
         "State plainly what two technical replicates can and cannot support.",
         240, "anywhere", ["w4-quant"])
    task("w4-attach", 4, "2026-12-12",
         "Attach Phase 2 plan and biosafety documentation",
         "Attach the Phase 2 plan and the biosafety documentation.",
         60, "anywhere", ["w4-writeup"])

    gates = [
        {
            "id": "g0-biosafety",
            "date": "2026-11-14",
            "question": "Is the biosafety determination signed, and is it BSL-1?",
            "on_fail": "BSL-2 means a BSL-2 facility with a qualified scientist, which is "
                       "not achievable by December 14. Phase 1 becomes the computational "
                       "fallback.",
            "requires": ["w0-determination", "w0-order-genes", "w0-order-reagents"],
        },
        {
            "id": "g1-dna",
            "date": "2026-11-23",
            "question": "Has the DNA arrived, and are glycerol stocks frozen for wild type "
                        "and R100K?",
            "on_fail": "Move to the fallback decision. Gene synthesis cannot be repeated "
                       "inside the window.",
            "requires": ["w1-dna-received", "w1-glycerol"],
        },
        {
            "id": "g2-protein",
            "date": "2026-12-06",
            "question": "Is purified wild type and R100K in hand, with a gel image "
                        "proving it?",
            "on_fail": "Week 4 has nothing to assay. Fall back to the written "
                       "interpretation of whatever gels exist, plus the Phase 2 plan.",
            "requires": ["w3-confirm-gel"],
        },
    ]

    forks = [
        {
            "id": "F1",
            "ask_date": "2026-11-10",
            "reask_until": "2026-11-14",
            "question": "What did the supervisor determine?",
            "options": [
                {"key": "bsl1", "label": "BSL-1 - may proceed in the school lab",
                 "effects": {"note": "Determination: BSL-1. In-school pathway stands."}},
                {"key": "bsl2", "label": "BSL-2 - not achievable by Dec 14",
                 "effects": {"flag": {"fallback_active": True},
                             "note": "Determination: BSL-2. Phase 1 becomes the "
                                     "computational fallback."}},
                {"key": "not_yet", "label": "Not yet determined", "defer": True,
                 "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F2",
            "ask_date": "2026-11-11",
            "reask_until": "2026-11-16",
            "question": "Which synthesis tier did you order, and what delivery date did "
                        "the supplier give?",
            "prompt_date": True,
            "date_label": "Supplier's delivery estimate",
            "options": [
                {"key": "express", "label": "Express (nearer 4 business days plus shipping)",
                 "effects": {"set_date": {"w1-dna-received": "from_answer"},
                             "note": "Express synthesis tier ordered."}},
                {"key": "standard", "label": "Standard (about 10 business days plus shipping)",
                 "effects": {"set_date": {"w1-dna-received": "from_answer"},
                             "note": "Standard synthesis tier ordered."}},
                {"key": "not_yet", "label": "Not ordered yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F3",
            "ask_date": "2026-11-13",
            "reask_until": "2026-12-01",
            "question": "Which freezing method will week 3 use?",
            "options": [
                {"key": "minus80", "label": "-80 C freezer, 15 min per cycle",
                 "effects": {"set_duration": {"w3-lysis": 240},
                             "note": "Lysis: -80 C, 15 min per cycle."}},
                {"key": "dryice", "label": "Dry ice and ethanol bath, about 5 min",
                 "effects": {"set_duration": {"w3-lysis": 240},
                             "note": "Lysis: dry ice and ethanol, equivalent fast freeze."}},
                {"key": "minus20", "label": "-20 C only, at least 1 hour per cycle",
                 "effects": {"set_duration": {"w3-lysis": 420},
                             "note": "Lysis: -20 C fallback. At least 1 hour per cycle, "
                                     "three cycles. Lyses less completely; the lysozyme "
                                     "step partly compensates."}},
                {"key": "not_yet", "label": "Not confirmed yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F4",
            "ask_date": "2026-11-16",
            "reask_until": "2026-11-30",
            "question": "Did the DNA arrive today?",
            "options": [
                {"key": "yes", "label": "Yes, it arrived",
                 "effects": {"complete": ["w1-dna-received"],
                             "set_date": {"w1-transform": "next_lab_day"},
                             "note": "DNA received."}},
                {"key": "no", "label": "Not yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F5",
            "ask_date": "2026-11-19",
            "reask_until": "2026-11-23",
            "question": "Colonies on the variant plates, and a clean negative control?",
            "options": [
                {"key": "good", "label": "Colonies present, negative control clean",
                 "effects": {"note": "Selection worked."}},
                {"key": "none", "label": "No colonies - use the repeat transformation",
                 "effects": {"activate": ["w1-retransform"],
                             "set_date": {"w1-retransform": "next_lab_day"},
                             "note": "No colonies. One repeat transformation fits in "
                                     "this week."}},
                {"key": "second_fail", "label": "No colonies on the repeat either",
                 "effects": {"flag": {"gate_g1_early": True},
                             "note": "Second transformation failure. The fallback "
                                     "decision moves forward to Nov 23."}},
                {"key": "not_yet", "label": "Plates not read yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F6",
            "ask_date": "2026-11-22",
            "reask_until": "2026-11-23",
            "question": "Do you have lab access on Nov 23-24?",
            "options": [
                {"key": "yes", "label": "Yes - run the small-scale test expression",
                 "effects": {"activate": ["w2-test-expr", "w2-test-gel", "w2-record"],
                             "note": "Lab access Nov 23-24. Test expression branch "
                                     "activated."}},
                {"key": "no", "label": "No - preparation work only",
                 "effects": {"note": "No lab access Nov 23-24. Preparation branch only."}},
                {"key": "not_yet", "label": "Do not know yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F7",
            "ask_date": "2026-11-24",
            "reask_until": "2026-11-25",
            "question": "Was there a visible induced band at the expected size?",
            "options": [
                {"key": "yes", "label": "Yes, band visible",
                 "effects": {"note": "Induced band confirmed. Most of the week 3 risk "
                                     "is removed."}},
                {"key": "no", "label": "No band visible",
                 "effects": {"note": "No induced band in the test expression. Week 3 "
                                     "carries full expression risk."}},
                {"key": "not_run", "label": "Test expression was not run", "defer": True,
                 "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F8",
            "ask_date": "2026-12-04",
            "reask_until": "2026-12-06",
            "question": "Is there a band at the expected size, enriched in the elution "
                        "lanes?",
            "options": [
                {"key": "yes", "label": "Yes - purified protein confirmed",
                 "effects": {"note": "Purified protein confirmed on gel."}},
                {"key": "no", "label": "No - elution empty or no enrichment",
                 "effects": {"flag": {"purification_failed": True},
                             "note": "No enriched elution band. Check the flow-through "
                                     "and wash to find where the protein went."}},
                {"key": "not_yet", "label": "Gel not run yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F9",
            "ask_date": "2026-12-04",
            "reask_until": "2026-12-09",
            "question": "Did R100A purify successfully?",
            "options": [
                {"key": "yes", "label": "Yes - R100A is available to assay",
                 "effects": {"flag": {"r100a_available": True},
                             "note": "R100A purified. Eligible for the spare day."}},
                {"key": "no", "label": "No - two variants only",
                 "effects": {"note": "R100A not available. Spare day held for a repeat "
                                     "run."}},
                {"key": "not_yet", "label": "Not known yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
        {
            "id": "F10",
            "ask_date": "2026-12-09",
            "reask_until": "2026-12-10",
            "question": "Did any gel fail? The spare day goes to a repeat before R100A.",
            "options": [
                {"key": "repeat", "label": "Yes - use the spare day for a repeat run",
                 "effects": {"note": "Spare day assigned to a repeat run."}},
                {"key": "r100a", "label": "No - use the spare day for the R100A assay",
                 "effects": {"note": "Spare day assigned to the R100A assay."}},
                {"key": "free", "label": "No - spare day not needed",
                 "effects": {"drop": ["w4-spare"],
                             "note": "Spare day not needed."}},
                {"key": "not_yet", "label": "Not known yet", "defer": True, "effects": {}},
            ],
            "answered_on": None, "answer": None,
        },
    ]

    return {
        "project": "LanM Phase 1",
        "start_date": "2026-11-09",
        "end_date": "2026-12-14",
        "last_schedulable_date": "2026-12-13",
        "thanksgiving_start": "2026-11-25",
        "thanksgiving_end": "2026-11-29",
        "lab_weekdays": [0, 1, 2, 3, 4],
        "daily_lab_capacity_min": 240,
        "weeks": [
            {"index": 0, "start": "2026-11-09", "end": "2026-11-15",
             "title": "Approvals and ordering",
             "exit_condition": "Biosafety determination signed, genes ordered with a "
                               "delivery estimate in hand, reagents ordered."},
            {"index": 1, "start": "2026-11-16", "end": "2026-11-22",
             "title": "Transformation and stocks",
             "exit_condition": "Glycerol stocks frozen and labelled for at least wild "
                               "type and R100K."},
            {"index": 2, "start": "2026-11-23", "end": "2026-11-29",
             "title": "Thanksgiving, low intensity",
             "exit_condition": "Buffers and metal stocks ready, quantification method "
                               "tested, and ideally one confirmed induced band."},
            {"index": 3, "start": "2026-11-30", "end": "2026-12-06",
             "title": "Expression, lysis, purification",
             "exit_condition": "Purified wild type and R100K in hand, with a gel image "
                               "proving it."},
            {"index": 4, "start": "2026-12-07", "end": "2026-12-13",
             "title": "Assay, quantification, write-up",
             "exit_condition": "A quantified result, a figure, and a written "
                               "interpretation ready to hand in the week of Dec 14."},
        ],
        "tasks": T,
        "gates": gates,
        "forks": forks,
        "state": {"flags": {}, "notes": []},
    }


# --------------------------------------------------------------------------
# load / save, tolerant of hand edits
# --------------------------------------------------------------------------

TASK_DEFAULTS = {
    "week": 0, "scheduled_date": None, "title": "(untitled)", "detail": "",
    "duration_min": 30, "location": "anywhere", "blocked_by": [], "status": "pending",
    "completed_date": None, "notes": "", "critical": False, "why": "", "lag_days": 0,
    "active": True,
}

VALID_STATUS = ("pending", "done", "skipped", "blocked")


def normalize(plan):
    """Fill in anything a hand edit left out, and coerce loose types.

    This is what makes plan.json safe to edit in a text editor: a missing field,
    a string where a number belongs, or an unknown status does not crash the page.
    """
    plan.setdefault("start_date", "2026-11-09")
    plan.setdefault("end_date", "2026-12-14")
    plan.setdefault("last_schedulable_date", "2026-12-13")
    plan.setdefault("thanksgiving_start", "2026-11-25")
    plan.setdefault("thanksgiving_end", "2026-11-29")
    plan.setdefault("lab_weekdays", [0, 1, 2, 3, 4])
    plan.setdefault("daily_lab_capacity_min", 240)
    plan.setdefault("weeks", [])
    plan.setdefault("tasks", [])
    plan.setdefault("gates", [])
    plan.setdefault("forks", [])
    st = plan.setdefault("state", {})
    st.setdefault("flags", {})
    st.setdefault("notes", [])

    seen = set()
    clean = []
    for t in plan["tasks"]:
        if not isinstance(t, dict) or not t.get("id"):
            continue
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        for k, v in TASK_DEFAULTS.items():
            if k not in t or t[k] is None and k in ("title", "detail", "notes", "why"):
                t[k] = list(v) if isinstance(v, list) else v
        try:
            t["duration_min"] = max(0, int(t["duration_min"]))
        except (TypeError, ValueError):
            t["duration_min"] = 30
        try:
            t["lag_days"] = max(0, int(t.get("lag_days") or 0))
        except (TypeError, ValueError):
            t["lag_days"] = 0
        try:
            t["week"] = int(t["week"])
        except (TypeError, ValueError):
            t["week"] = 0
        if t["location"] not in ("lab", "anywhere"):
            t["location"] = "anywhere"
        if t["status"] not in VALID_STATUS:
            t["status"] = "pending"
        if not isinstance(t["blocked_by"], list):
            t["blocked_by"] = []
        t["blocked_by"] = [b for b in t["blocked_by"] if isinstance(b, str)]
        t["active"] = bool(t.get("active", True))
        t["critical"] = bool(t.get("critical", False))
        # a date that will not parse falls back to the project start
        try:
            pd(t["scheduled_date"])
        except ValueError:
            t["scheduled_date"] = plan["start_date"]
        if not t["scheduled_date"]:
            t["scheduled_date"] = plan["start_date"]
        try:
            pd(t["completed_date"])
        except ValueError:
            t["completed_date"] = None
        clean.append(t)
    plan["tasks"] = clean

    # drop blocked_by references to ids that no longer exist
    ids = {t["id"] for t in clean}
    for t in clean:
        t["blocked_by"] = [b for b in t["blocked_by"] if b in ids and b != t["id"]]

    for g in plan["gates"]:
        g.setdefault("requires", [])
        g.setdefault("on_fail", "")
        g.setdefault("question", "")
    for f in plan["forks"]:
        f.setdefault("options", [])
        f.setdefault("answered_on", None)
        f.setdefault("answer", None)
        f.setdefault("reask_until", f.get("ask_date"))
    return plan


def load_plan():
    with open(PLAN_PATH, "r", encoding="utf-8") as fh:
        return normalize(json.load(fh))


def save_plan(plan):
    tmp = PLAN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, PLAN_PATH)


def load_log():
    if not os.path.exists(LOG_PATH):
        return {"entries": []}
    with open(LOG_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return {"entries": []}
    return data


def append_log(entry):
    log = load_log()
    log["entries"].append(entry)
    tmp = LOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, LOG_PATH)


# --------------------------------------------------------------------------
# calendar rules
# --------------------------------------------------------------------------

def in_thanksgiving(plan, d):
    return pd(plan["thanksgiving_start"]) <= d <= pd(plan["thanksgiving_end"])


def day_allows(plan, d, task):
    """Rule 1 and rule 4: where a task may legally sit."""
    if task["location"] == "lab":
        if d.weekday() not in plan["lab_weekdays"]:
            return False
        if in_thanksgiving(plan, d):
            return False          # rule 4: never schedule a lab task Nov 25-29
    return True


def find_slot(plan, earliest, task, occupied):
    """First date on or after `earliest` this task may occupy.

    Lab tasks respect weekday, Thanksgiving, and the daily lab-minute cap. A task
    longer than the whole daily cap is still allowed to take an otherwise empty day,
    so an oversized task cannot loop forever.
    """
    d = earliest
    horizon = pd(plan["last_schedulable_date"]) + timedelta(days=120)
    cap = plan["daily_lab_capacity_min"]
    while d <= horizon:
        if day_allows(plan, d, task):
            if task["location"] != "lab":
                return d
            used = occupied.get(ds(d), 0)
            if used == 0 or used + task["duration_min"] <= cap:
                return d
        d += timedelta(days=1)
    return d


def next_lab_day(plan, after):
    d = after + timedelta(days=1)
    for _ in range(400):
        if d.weekday() in plan["lab_weekdays"] and not in_thanksgiving(plan, d):
            return d
        d += timedelta(days=1)
    return d


def topo_order(plan):
    """Task ids with every blocker ahead of the tasks it blocks. Cycles, which a
    hand edit can introduce, are broken rather than raised."""
    tasks = {t["id"]: t for t in plan["tasks"]}
    done, active, out = set(), set(), []

    def visit(tid):
        if tid in done or tid in active:
            return                      # already placed, or a cycle: break it here
        active.add(tid)
        for bid in tasks[tid]["blocked_by"]:
            if bid in tasks:
                visit(bid)
        active.discard(tid)
        done.add(tid)
        out.append(tid)

    for t in sorted(plan["tasks"], key=lambda t: (t["scheduled_date"], t["id"])):
        visit(t["id"])
    return out


def recompute(plan):
    """Rules 1 and 2.

    A task that already sits on a legal day and starts no earlier than its
    blockers stays exactly where it is. The daily lab cap governs where a task
    that *has* to move lands; it never re-plans a date the plan already holds,
    because the procedure itself schedules days longer than the cap (Dec 1 is
    300 minutes, Dec 8 is 360).

    Walking in topological order settles every blocker before its dependents, so
    one roll cascades through the whole chain in a single pass. The outer loop is
    a safety net for graphs a hand edit has made cyclic.
    """
    tasks = {t["id"]: t for t in plan["tasks"]}
    order = topo_order(plan)

    for _ in range(6):
        changed = False
        occupied = defaultdict(int)

        for tid in order:
            t = tasks[tid]
            if not t.get("active", True) or t["status"] == "done":
                continue

            floor = None
            for bid in t["blocked_by"]:
                b = tasks.get(bid)
                if not b or not b.get("active", True):
                    continue
                bdate = (pd(b["completed_date"]) if b["status"] == "done"
                         else pd(b["scheduled_date"]))
                need = bdate + timedelta(days=t["lag_days"])
                if floor is None or need > floor:
                    floor = need

            cur = pd(t["scheduled_date"])
            if (floor is None or cur >= floor) and day_allows(plan, cur, t):
                slot = cur                      # anchored: leave it alone
            else:
                slot = find_slot(plan, max(cur, floor) if floor else cur, t, occupied)

            if ds(slot) != t["scheduled_date"]:
                t["scheduled_date"] = ds(slot)
                changed = True
            if t["location"] == "lab":
                occupied[ds(slot)] += t["duration_min"]

        if not changed:
            break
    return plan


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------

def task_map(plan):
    return {t["id"]: t for t in plan["tasks"]}


def is_open(t):
    return t.get("active", True) and t["status"] != "done"


def blockers_outstanding(plan, t):
    tm = task_map(plan)
    out = []
    for bid in t["blocked_by"]:
        b = tm.get(bid)
        if b and b.get("active", True) and b["status"] != "done":
            out.append(b)
    return out


def downstream_ids(plan, start_id):
    """Every task reachable from start_id by following blocked_by edges forward."""
    fwd = defaultdict(list)
    for t in plan["tasks"]:
        for b in t["blocked_by"]:
            fwd[b].append(t["id"])
    seen, stack = set(), [start_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(fwd.get(cur, []))
    return seen


def gate_threatened_by(plan, task_id):
    """The earliest gate that this task, or anything downstream of it, feeds."""
    reach = downstream_ids(plan, task_id)
    hits = [g for g in plan["gates"] if set(g["requires"]) & reach]
    hits.sort(key=lambda g: g["date"])
    return hits[0] if hits else None


def gate_report(plan, today):
    """Rule 5: a gate whose date has passed with unmet requirements has failed."""
    tm = task_map(plan)
    failed, upcoming = [], []
    for g in sorted(plan["gates"], key=lambda g: g["date"]):
        unmet = [tm[r] for r in g["requires"] if r in tm and tm[r]["status"] != "done"]
        gd = pd(g["date"])
        if gd < today and unmet:
            failed.append({"gate": g, "unmet": unmet, "days_past": (today - gd).days})
        elif gd >= today:
            upcoming.append({"gate": g, "unmet": unmet, "days_until": (gd - today).days})
    return failed, upcoming


def overrun_report(plan):
    """Rule 3: anything pushed past the last schedulable day, named loudly."""
    last = pd(plan["last_schedulable_date"])
    out = []
    for t in plan["tasks"]:
        if not is_open(t):
            continue
        d = pd(t["scheduled_date"])
        if d > last:
            g = gate_threatened_by(plan, t["id"])
            out.append({"task": t, "days": (d - last).days, "gate": g})
    # critical-path overruns lead, then the longest overrun
    out.sort(key=lambda r: (not r["task"]["critical"], -r["days"], r["task"]["id"]))
    return out


def slack_report(plan, today):
    """Rule 6: working days available minus working days of pending lab tasks."""
    last = pd(plan["last_schedulable_date"])
    cap = plan["daily_lab_capacity_min"]
    lab_days = 0
    d = today
    while d <= last:
        if d.weekday() in plan["lab_weekdays"] and not in_thanksgiving(plan, d):
            lab_days += 1
        d += timedelta(days=1)
    pending_min = sum(t["duration_min"] for t in plan["tasks"]
                      if is_open(t) and t["location"] == "lab")
    needed = math.ceil(pending_min / cap) if cap else 0
    return {"lab_days": lab_days, "pending_min": pending_min,
            "needed_days": needed, "slack": lab_days - needed}


def week_for(plan, today):
    for w in plan["weeks"]:
        if pd(w["start"]) <= today <= pd(w["end"]):
            return w
    return plan["weeks"][-1] if plan["weeks"] else None


def due_forks(plan, today):
    out = []
    for f in plan["forks"]:
        if f.get("answered_on"):
            continue
        ask = pd(f.get("ask_date"))
        until = pd(f.get("reask_until")) or ask
        if ask and ask <= today <= (until or ask):
            out.append(f)
    return out


def overdue_forks(plan, today):
    out = []
    for f in plan["forks"]:
        if f.get("answered_on"):
            continue
        until = pd(f.get("reask_until")) or pd(f.get("ask_date"))
        if until and until < today:
            out.append(f)
    return out


def day_lists(plan, today):
    """The three ordered groups the morning view shows.

    Within a group, ties break on the task's position in plan.json, which is the
    order the procedure document lists its steps in. Sorting on id instead would
    put 'draft the containment section' before 'write the specification'.
    """
    seq = {t["id"]: i for i, t in enumerate(plan["tasks"])}
    overdue, scheduled = [], []
    for t in plan["tasks"]:
        if not is_open(t):
            continue
        d = pd(t["scheduled_date"])
        if d < today:
            overdue.append(t)
        elif d == today:
            scheduled.append(t)
    overdue.sort(key=lambda t: (t["scheduled_date"], not t["critical"], seq[t["id"]]))
    scheduled.sort(key=lambda t: (not t["critical"], seq[t["id"]]))

    shown = {t["id"] for t in overdue + scheduled}
    pull = []
    horizon = today + timedelta(days=7)
    for t in plan["tasks"]:
        if not is_open(t) or t["id"] in shown:
            continue
        if t["location"] != "anywhere":
            continue
        d = pd(t["scheduled_date"])
        if today < d <= horizon and not blockers_outstanding(plan, t):
            pull.append(t)
    pull.sort(key=lambda t: (t["scheduled_date"], seq[t["id"]]))
    return overdue, scheduled, pull[:3]


# --------------------------------------------------------------------------
# fork effects
# --------------------------------------------------------------------------

def resolve_date(plan, spec, checkin, fork):
    if spec == "today":
        return ds(checkin)
    if spec == "tomorrow":
        return ds(checkin + timedelta(days=1))
    if spec == "next_lab_day":
        return ds(next_lab_day(plan, checkin))
    if spec == "from_answer":
        val = (fork or {}).get("answer_value")
        try:
            return ds(pd(val))
        except (ValueError, TypeError):
            return ds(checkin + timedelta(days=1))
    if isinstance(spec, str) and spec.startswith("+"):
        try:
            return ds(checkin + timedelta(days=int(spec[1:])))
        except ValueError:
            return ds(checkin)
    try:
        return ds(pd(spec))
    except (ValueError, TypeError):
        return ds(checkin)


def apply_effects(plan, eff, checkin, fork=None):
    tm = task_map(plan)
    for tid in eff.get("activate", []):
        if tid in tm:
            tm[tid]["active"] = True
    for tid in eff.get("drop", []):
        if tid in tm:
            tm[tid]["active"] = False
    for tid in eff.get("complete", []):
        if tid in tm:
            tm[tid]["status"] = "done"
            tm[tid]["completed_date"] = ds(checkin)
    for tid, mins in (eff.get("set_duration") or {}).items():
        if tid in tm:
            try:
                tm[tid]["duration_min"] = max(0, int(mins))
            except (TypeError, ValueError):
                pass
    for tid, spec in (eff.get("set_date") or {}).items():
        if tid in tm:
            tm[tid]["scheduled_date"] = resolve_date(plan, spec, checkin, fork)
    for k, v in (eff.get("flag") or {}).items():
        plan["state"]["flags"][k] = v
    if eff.get("note"):
        plan["state"]["notes"].append({"date": ds(checkin), "text": eff["note"]})


# --------------------------------------------------------------------------
# check-in
# --------------------------------------------------------------------------

def submit_checkin(plan, checkin, form):
    """Rules 1-2: close what is done, roll what is not, then cascade."""
    tm = task_map(plan)
    shown_ids = form.get("shown", [""])[0].split(",")
    shown_ids = [s for s in shown_ids if s]

    entry = {
        "date": ds(checkin),
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
        "day_note": form.get("day_note", [""])[0].strip(),
        "tasks": [],
        "forks": [],
    }

    # forks first: their effects can activate or re-date tasks
    for f in plan["forks"]:
        key = form.get("fork_" + f["id"], [""])[0]
        if not key:
            continue
        opt = next((o for o in f["options"] if o.get("key") == key), None)
        if not opt:
            continue
        if f.get("prompt_date"):
            f["answer_value"] = form.get("forkdate_" + f["id"], [""])[0].strip()
        entry["forks"].append({"id": f["id"], "answer": key,
                               "value": f.get("answer_value")})
        apply_effects(plan, opt.get("effects") or {}, checkin, f)
        if not opt.get("defer"):
            f["answered_on"] = ds(checkin)
            f["answer"] = key

    # then the task outcomes
    for tid in shown_ids:
        t = tm.get(tid)
        if not t:
            continue
        outcome = form.get("o_" + tid, [""])[0]
        note = form.get("n_" + tid, [""])[0].strip()
        if note:
            stamp = f"[{ds(checkin)}] {note}"
            t["notes"] = (t["notes"] + "\n" + stamp).strip() if t["notes"] else stamp
        entry["tasks"].append({"id": tid, "outcome": outcome or "untouched",
                               "note": note})

        if outcome == "done":
            t["status"] = "done"
            t["completed_date"] = ds(checkin)
        elif outcome in ("skipped", "blocked"):
            t["status"] = outcome
            t["scheduled_date"] = ds(checkin + timedelta(days=1))
        else:
            # left unticked: rolls like a skip but keeps its status
            if pd(t["scheduled_date"]) <= checkin:
                t["scheduled_date"] = ds(checkin + timedelta(days=1))

    recompute(plan)
    save_plan(plan)
    append_log(entry)
    return entry


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def esc(s):
    return html.escape(str(s if s is not None else ""))


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f5f4f1; --card:#fff; --ink:#15150f; --mute:#6a675f; --line:#d8d5cd;
  --accent:#0a4f8c; --accent-bg:#e7f0f8; --warn:#9c2d08; --warn-bg:#fbeae3;
}
body{background:var(--bg);color:var(--ink);
  font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-text-size-adjust:100%}
.wrap{max-width:780px;margin:0 auto;padding:14px 14px 56px}
a{color:var(--accent)}
h1{font-size:17px;font-weight:650;letter-spacing:-.01em}
h2{font-size:12px;font-weight:650;text-transform:uppercase;letter-spacing:.07em;
  color:var(--mute);margin:20px 0 7px;border-bottom:1px solid var(--line);padding-bottom:4px}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.toggle{font-size:13px}
.toggle a{display:inline-block;padding:3px 9px;border:1px solid var(--line);
  background:var(--card);text-decoration:none;color:var(--mute)}
.toggle a.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.meta{color:var(--mute);font-size:13px;margin-top:2px}
.exit{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--ink);
  padding:8px 11px;margin-top:11px;font-size:14px}
.exit b{font-weight:650}
.stat{display:grid;grid-template-columns:1fr 1fr;margin-top:11px;
  border:1px solid var(--line);background:var(--card)}
.stat>div{padding:7px 11px;border-right:1px solid var(--line);
  border-top:1px solid var(--line)}
.stat>div:nth-child(-n+2){border-top:0}
.stat>div:nth-child(2n){border-right:0}
@media (min-width:560px){
  .stat{grid-template-columns:repeat(4,1fr)}
  .stat>div{border-top:0;border-right:1px solid var(--line)}
  .stat>div:last-child{border-right:0}
}
.stat .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
.stat .v{font-size:17px;font-weight:650}
.stat .v.bad{color:var(--warn)}
.banner{border:1px solid var(--warn);background:var(--warn-bg);padding:11px 13px;
  margin-top:13px;border-left:4px solid var(--warn)}
.banner h3{color:var(--warn);font-size:14px;font-weight:700;margin-bottom:4px}
.banner p{font-size:14px;margin-top:5px}
.banner ul{margin:5px 0 0 17px;font-size:14px}
.gatebox{background:var(--card);border:1px solid var(--line);padding:9px 11px;margin-top:11px;
  border-left:3px solid var(--accent)}
.gatebox .q{font-weight:600}
.gatebox .when{font-size:13px;color:var(--mute)}
.card{background:var(--card);border:1px solid var(--line);padding:9px 11px;margin-bottom:7px}
.card.crit{border-left:3px solid var(--accent)}
.card.late{border-left:3px solid var(--warn)}
.card.off{opacity:.55;background:#efeee9}
.card .t{font-weight:600;font-size:15px}
.card .d{font-size:13.5px;color:#3a382f;margin-top:3px}
.card .f{font-size:12px;color:var(--mute);margin-top:5px;
  display:flex;gap:9px;flex-wrap:wrap;align-items:center}
.tag{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:1px 5px;
  border:1px solid currentColor;font-weight:650}
.tag.c{color:var(--accent);background:var(--accent-bg)}
.tag.w{color:var(--warn);background:var(--warn-bg)}
.why{font-size:12.5px;color:var(--accent);margin-top:4px}
.blk{font-size:12.5px;color:var(--warn);margin-top:4px}
.none{color:var(--mute);font-size:13.5px;padding:5px 0}
fieldset{border:1px solid var(--line);background:var(--card);padding:9px 11px;margin-bottom:7px}
fieldset.crit{border-left:3px solid var(--accent)}
legend{font-weight:600;padding:0 5px;font-size:15px}
.opts{display:flex;gap:13px;flex-wrap:wrap;margin:6px 0 5px;font-size:14px}
.opts label{cursor:pointer;display:flex;align-items:center;gap:4px}
input[type=text],textarea,input[type=date]{width:100%;border:1px solid var(--line);
  padding:5px 7px;font:inherit;font-size:14px;background:#fdfdfc;color:var(--ink)}
textarea{min-height:46px;resize:vertical}
.forkbox{border:1px solid var(--accent);background:var(--accent-bg);padding:10px 12px;
  margin-bottom:8px}
.forkbox legend{color:var(--accent)}
.forkbox .opts{flex-direction:column;gap:5px}
button{background:var(--ink);color:#fff;border:0;padding:11px 19px;font:inherit;
  font-weight:650;cursor:pointer;width:100%;font-size:15px}
.notes{font-size:12.5px;color:var(--mute);margin-top:4px;white-space:pre-wrap}
.log{font-size:13px;color:var(--mute);margin-top:9px}
@media (min-width:620px){ button{width:auto} }
"""


def page(title, body):
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head>"
        f"<body><div class=wrap>{body}</div></body></html>"
    )


def dur(mins):
    if mins >= 60:
        h, m = divmod(mins, 60)
        return f"{h}h{m:02d}" if m else f"{h}h"
    return f"{mins}m"


def render_card(plan, t, today):
    blockers = blockers_outstanding(plan, t)
    d = pd(t["scheduled_date"])
    late = d < today
    cls = "card"
    if blockers:
        cls += " off"
    elif t["critical"]:
        cls += " crit"
    if late and not blockers:
        cls += " late"

    tags = []
    if t["critical"]:
        tags.append("<span class='tag c'>critical path</span>")
    if late:
        tags.append(f"<span class='tag w'>overdue {plural((today - d).days, 'day')}</span>")
    if t["status"] == "blocked":
        tags.append("<span class='tag w'>blocked</span>")
    if t["status"] == "skipped":
        tags.append("<span class='tag w'>skipped</span>")

    out = [f"<div class='{cls}'><div class=t>{esc(t['title'])}</div>"]
    if t["detail"]:
        out.append(f"<div class=d>{esc(t['detail'])}</div>")
    if t["critical"] and t["why"]:
        out.append(f"<div class=why>Why it matters: {esc(t['why'])}</div>")
    if blockers:
        names = ", ".join(f"{esc(b['title'])} ({esc(b['id'])})" for b in blockers)
        out.append(f"<div class=blk>Blocked by {names}</div>")
    if t["notes"]:
        out.append(f"<div class=notes>{esc(t['notes'])}</div>")
    out.append(
        f"<div class=f><span>{dur(t['duration_min'])}</span>"
        f"<span>{esc(t['location'])}</span>"
        f"<span>week {t['week']}</span>"
        f"<span>{esc(t['id'])}</span>" + "".join(tags) + "</div></div>"
    )
    return "".join(out)


def render_morning(plan, today, is_default_evening):
    failed, upcoming = gate_report(plan, today)
    overruns = overrun_report(plan)
    sl = slack_report(plan, today)
    wk = week_for(plan, today)
    overdue, scheduled, pull = day_lists(plan, today)
    flags = plan["state"]["flags"]
    days_left = (pd(plan["end_date"]) - today).days

    b = []
    b.append(
        "<div class=top><div><h1>LanM Phase 1</h1>"
        f"<div class=meta>{esc(human(today))} {today.year} &middot; "
        f"{plural(days_left, 'day')} to Dec 14</div></div>"
        f"<div class=toggle><a class=on href='?date={ds(today)}&view=morning'>Morning</a>"
        f"<a href='?date={ds(today)}&view=evening'>Evening</a></div></div>"
    )

    # Rule 5: a failed gate leads, ahead of the task list.
    for fr in failed:
        g = fr["gate"]
        names = "".join(
            f"<li>{esc(t['title'])} ({esc(t['id'])}) &mdash; {esc(t['status'])}</li>"
            for t in fr["unmet"])
        b.append(
            f"<div class=banner><h3>Gate failed: {esc(g['id'])}, "
            f"{esc(human(pd(g['date'])))}, {plural(fr['days_past'], 'day')} ago</h3>"
            f"<p><b>{esc(g['question'])}</b></p>"
            f"<p>Fallback branch: {esc(g['on_fail'])}</p>"
            f"<p>Unmet:</p><ul>{names}</ul></div>"
        )

    if flags.get("fallback_active"):
        b.append(
            "<div class=banner><h3>Computational fallback is active</h3>"
            "<p>The determination came back BSL-2. The wet-lab pathway is closed for "
            "Phase 1.</p></div>"
        )

    # Rule 3: overrun past the last schedulable day, named loudly.
    if overruns:
        items = []
        for r in overruns:
            if r["gate"]:
                gt = (f" Threatens gate {esc(r['gate']['id'])}, "
                      f"{esc(human(pd(r['gate']['date'])))}: "
                      f"{esc(r['gate']['question'])}")
            else:
                # nothing downstream is a gate, so what it threatens is the hand-in
                gt = (f" Threatens the {esc(human(pd(plan['end_date'])))} hand-in "
                      f"directly &mdash; no gate sits between this and the deliverable.")
            crit = " <span class='tag w'>critical path</span>" if r["task"]["critical"] else ""
            items.append(
                f"<li><b>{esc(r['task']['title'])}</b> ({esc(r['task']['id'])}){crit} is "
                f"{plural(r['days'], 'day')} past Dec 13, now {esc(r['task']['scheduled_date'])}."
                f"{gt}</li>")
        b.append(
            f"<div class=banner><h3>{plural(len(overruns), 'task')} pushed past Dec 13</h3>"
            f"<ul>{''.join(items)}</ul></div>")

    od = overdue_forks(plan, today)
    if od:
        items = "".join(f"<li>{esc(f['question'])} (asked {esc(f['ask_date'])})</li>"
                        for f in od)
        b.append(f"<div class=banner><h3>Unanswered questions</h3><ul>{items}</ul></div>")

    if wk:
        b.append(
            f"<div class=exit><b>Week {wk['index']} &middot; {esc(wk['title'])}.</b> "
            f"Exit condition: {esc(wk['exit_condition'])}</div>")

    nxt = upcoming[0] if upcoming else None
    if nxt:
        g = nxt["gate"]
        unmet_n = len(nxt["unmet"])
        b.append(
            f"<div class=gatebox><div class=q>Next gate &middot; {esc(g['id'])}: "
            f"{esc(g['question'])}</div>"
            f"<div class=when>{esc(human(pd(g['date'])))} &middot; in "
            f"{plural(nxt['days_until'], 'day')} &middot; "
            f"{unmet_n} of {len(g['requires'])} requirements still open</div>"
            f"<div class=when>On fail: {esc(g['on_fail'])}</div></div>")

    slack_cls = "v bad" if sl["slack"] < 0 else "v"
    b.append(
        "<div class=stat>"
        f"<div><div class=k>Days to Dec 14</div><div class=v>{days_left}</div></div>"
        f"<div><div class=k>Lab days left</div><div class=v>{sl['lab_days']}</div></div>"
        f"<div><div class=k>Lab days needed</div><div class=v>{sl['needed_days']}</div></div>"
        f"<div><div class=k>Slack</div><div class='{slack_cls}'>{sl['slack']:+d}</div></div>"
        "</div>")

    b.append("<h2>Rolled over</h2>")
    b.append("".join(render_card(plan, t, today) for t in overdue)
             or "<div class=none>Nothing overdue.</div>")

    b.append("<h2>Today</h2>")
    b.append("".join(render_card(plan, t, today) for t in scheduled)
             or "<div class=none>Nothing scheduled for today.</div>")

    b.append("<h2>If you have spare time</h2>")
    b.append("".join(render_card(plan, t, today) for t in pull)
             or "<div class=none>Nothing can be pulled forward.</div>")

    if is_default_evening:
        b.append(f"<div class=log>It is past {EVENING_HOUR}:00 &mdash; "
                 f"<a href='?date={ds(today)}&view=evening'>check in for tonight</a>.</div>")
    return page("LanM morning", "".join(b))


def render_evening(plan, today):
    overdue, scheduled, pull = day_lists(plan, today)
    shown = overdue + scheduled + pull
    forks = due_forks(plan, today)

    b = []
    b.append(
        "<div class=top><div><h1>Evening check-in</h1>"
        f"<div class=meta>{esc(human(today))} {today.year} &middot; "
        f"{plural(len(shown), 'task')} shown this morning</div></div>"
        f"<div class=toggle><a href='?date={ds(today)}&view=morning'>Morning</a>"
        f"<a class=on href='?date={ds(today)}&view=evening'>Evening</a></div></div>")

    b.append(f"<form method=post action='/submit'>"
             f"<input type=hidden name=date value='{ds(today)}'>"
             f"<input type=hidden name=shown value='{','.join(t['id'] for t in shown)}'>")

    if forks:
        b.append("<h2>Questions due today</h2>")
        for f in forks:
            opts = "".join(
                f"<label><input type=radio name='fork_{esc(f['id'])}' "
                f"value='{esc(o['key'])}'> {esc(o['label'])}</label>"
                for o in f["options"])
            extra = ""
            if f.get("prompt_date"):
                extra = (f"<div style='margin-top:6px'>"
                         f"<div class=meta>{esc(f.get('date_label', 'Date'))}</div>"
                         f"<input type=date name='forkdate_{esc(f['id'])}'></div>")
            b.append(
                f"<fieldset class=forkbox><legend>{esc(f['id'])}</legend>"
                f"<div style='font-weight:600'>{esc(f['question'])}</div>"
                f"<div class=opts>{opts}</div>{extra}</fieldset>")

    b.append("<h2>Tasks</h2>")
    if not shown:
        b.append("<div class=none>Nothing was on the list today.</div>")
    for t in shown:
        cls = "crit" if t["critical"] else ""
        blockers = blockers_outstanding(plan, t)
        sub = []
        if t["critical"] and t["why"]:
            sub.append(f"<div class=why>{esc(t['why'])}</div>")
        if blockers:
            names = ", ".join(esc(x["title"]) for x in blockers)
            sub.append(f"<div class=blk>Blocked by {names}</div>")
        b.append(
            f"<fieldset class='{cls}'><legend>{esc(t['title'])}</legend>"
            f"<div class=f style='color:var(--mute);font-size:12px'>"
            f"{dur(t['duration_min'])} &middot; {esc(t['location'])} &middot; "
            f"{esc(t['id'])}</div>"
            + "".join(sub) +
            f"<div class=opts>"
            f"<label><input type=radio name='o_{esc(t['id'])}' value=done> done</label>"
            f"<label><input type=radio name='o_{esc(t['id'])}' value=skipped> skipped</label>"
            f"<label><input type=radio name='o_{esc(t['id'])}' value=blocked> blocked</label>"
            f"</div>"
            f"<input type=text name='n_{esc(t['id'])}' placeholder='note'>"
            f"</fieldset>")

    b.append("<h2>The day overall</h2>"
             "<fieldset><textarea name=day_note "
             "placeholder='Anything about today as a whole'></textarea></fieldset>"
             "<div style='margin-top:11px'><button type=submit>"
             "Submit check-in and recompute</button></div>"
             "<div class=log>Writes one entry to log.json, then rewrites plan.json. "
             "Anything left unticked rolls to the next day it can run.</div></form>")
    return page("LanM evening", "".join(b))


# --------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    base_today = None

    def _today(self, qs):
        if qs.get("date"):
            try:
                return pd(qs["date"][0])
            except ValueError:
                pass
        if Handler.base_today:
            return Handler.base_today
        return date.today()

    def _send(self, body, code=200, ctype="text/html; charset=utf-8"):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path not in ("/", "/index.html"):
            self._send(page("Not found", "<h1>Not found</h1>"), 404)
            return
        try:
            # re-read from disk every request, so a hand edit shows up on reload
            plan = load_plan()
        except Exception as exc:                                  # noqa: BLE001
            self._send(page("plan.json problem",
                            "<h1>plan.json could not be read</h1>"
                            f"<div class=banner><h3>{esc(type(exc).__name__)}</h3>"
                            f"<p>{esc(exc)}</p>"
                            "<p>Fix the file and reload. Nothing was changed.</p></div>"),
                       500)
            return
        today = self._today(qs)
        now_evening = datetime.now().hour >= EVENING_HOUR
        view = qs.get("view", [""])[0]
        if view not in ("morning", "evening"):
            view = "evening" if now_evening else "morning"
        if view == "evening":
            self._send(render_evening(plan, today))
        else:
            self._send(render_morning(plan, today, now_evening))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/submit":
            self._send(page("Not found", "<h1>Not found</h1>"), 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        plan = load_plan()
        try:
            checkin = pd(form.get("date", [""])[0])
        except ValueError:
            checkin = None
        if not checkin:
            checkin = Handler.base_today or date.today()
        submit_checkin(plan, checkin, form)
        nxt = checkin + timedelta(days=1)
        self.send_response(303)
        self.send_header("Location", f"/?date={ds(nxt)}&view=morning")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser(description="LanM Phase 1 daily dashboard")
    ap.add_argument("--today", help="pretend it is this date, YYYY-MM-DD")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--seed", action="store_true",
                    help="rewrite plan.json and log.json from the seed, then exit")
    args = ap.parse_args()

    if args.seed or not os.path.exists(PLAN_PATH):
        plan = normalize(seed_plan())
        recompute(plan)
        save_plan(plan)
        if args.seed or not os.path.exists(LOG_PATH):
            with open(LOG_PATH, "w", encoding="utf-8") as fh:
                json.dump({"entries": []}, fh, indent=2)
                fh.write("\n")
        print(f"seeded {PLAN_PATH} ({len(plan['tasks'])} tasks, "
              f"{len(plan['gates'])} gates, {len(plan['forks'])} forks)")
        if args.seed:
            return

    if args.today:
        Handler.base_today = pd(args.today)

    srv = HTTPServer((args.host, args.port), Handler)
    print(f"LanM dashboard on http://localhost:{args.port}")
    if args.host == "0.0.0.0":
        print("Reachable from other devices on this network. No login: anyone on the "
              "network can read and submit.")
    if Handler.base_today:
        print(f"Simulated date: {Handler.base_today}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
