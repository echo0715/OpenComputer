# Task Coverage Gap Analysis

Generated: 2026-05-08. Use this to guide task extension work across all apps.

---

## Summary: Apps by Task Count

| App | Tasks | Priority | Main Gap |
|-----|-------|----------|----------|
| galculator | 8 | HIGH | Only arithmetic; missing scientific mode, tape mode |
| writer (libreoffice_writer prefix) | 10 | HIGH | Only content tasks; missing settings, styles, export |
| brave | 18 | HIGH | Only web navigation; missing settings/preferences |
| chrome | 20 | MEDIUM | Only local/download tasks; missing settings |
| drawio | 20 | MEDIUM | Missing complex workflows, export, page management |
| firefox | 20 | MEDIUM | Has proposals/evaluated; needs Stage 3 finalization |
| gedit | 21 | MEDIUM | Has 16 proposals; needs evaluation + finalization |
| kdenlive | 20 | MEDIUM | Has 15 proposals; needs evaluation + finalization |
| pcmanfm | 20 | MEDIUM | Has 15 proposals; needs evaluation + finalization |
| shotcut | 20 | MEDIUM | No proposals; missing settings, complex timelines |
| zoom | 20 | MEDIUM | Mostly single-setting tasks; missing combined workflows |
| krita | 21 | LOW | Has proposals/evaluated; missing animation, resources |

---

## App-by-App Gap Analysis

### galculator (8 tasks)

**Already covered:**
- Compound arithmetic with parentheses
- Hex mode arithmetic
- Large multiplication
- Memory accumulate/mean
- Multi-step division chains
- Negative results
- Nested parentheses (scientific mode)
- Reciprocal chains

**Missing:**
- Scientific mode: sin/cos/tan/asin/acos/atan inputs and verification
- Scientific mode: log, ln, exp, sqrt, x^y
- Paper mode: multi-step tape operations (running total verification via display)
- Percentage calculations (e.g., 200 * 15% = 30)
- Binary/octal mode arithmetic
- Clear/AC behavior after chained operations
- Mode switching mid-calculation
- Factorial, combinations/permutations (scientific mode)

**Verifiability:** HIGH — galculator verifier reads display via AT-SPI. All computations verify via `check-display-value`. Paper mode and mode switches verify via `mode` endpoint.

---

### brave (18 tasks)

**Already covered:**
- Multi-tab navigation (httpbin.org, Wikipedia)
- Bookmarks (create, visit, organize)
- Cookie inspection
- DOM inspection
- PNG download verification
- Form filling (pizza form)
- Multi-step form validation
- HTTP headers/user-agent inspection
- History trail
- Query params chain
- Basic auth flows
- Status codes survey
- Research/compare tabs

**Missing:**
- Browser settings: default search engine, homepage, startup pages
- Privacy shields (Brave-specific ad/tracker blocking)
- Downloads: change default download directory
- Appearance: font size, zoom level, theme
- Extension management (install/enable/disable)
- History: clear browsing data
- Cookies settings (block third-party, clear on close)
- Site settings (camera, location, notifications)
- Bookmark folder organization (create folder, move bookmarks)
- Reading list

**Verifiability:** MEDIUM — browser verifier can check tabs, bookmarks, history, cookies. Settings stored in profile JSON/SQLite. Download dir stored in Preferences JSON. Extension state readable from profile.

---

### chrome (20 tasks)

**Already covered:**
- Local HTML viewing (calendar, cart, dashboard, data viz, form, JSON, kanban, log filter, markdown, math, multi-step, notes, styled, SVG, multi-tab)
- Wikipedia + history
- Download from httpbin

**Missing:**
- Chrome settings: default search engine, homepage, startup
- Extensions: install/enable/disable
- Appearance: theme, font size, zoom
- Privacy settings: cookies, site data, tracking
- Downloads directory configuration
- Passwords and autofill settings
- Site-specific settings (notifications, camera, location)
- History management (clear, delete specific sites)
- Incognito window tasks
- Tab groups

**Verifiability:** MEDIUM — verifier can check tabs, bookmarks, history (SQLite), downloads (JSON). Settings readable from Preferences file.

---

### drawio (20 tasks)

**Already covered:**
- AWS cloud diagram
- BPMN process
- Edit shapes
- Edit + add shapes
- ER diagram
- Fix and color
- Floorplan
- Flowchart
- Incident response
- Kubernetes diagram
- Mind map
- Multipage diagram
- Network diagram
- Restyle diagram
- State machine
- Styled data
- Styled process
- Swimlane
- UML class
- More

**Missing:**
- Export to PNG/PDF with specific settings
- Page management (add, rename, reorder, delete pages)
- Custom templates
- Shape libraries (enable/disable)
- Grid and snap settings
- Printing/page setup
- Group and ungroup operations
- Complex layered diagrams
- Hyperlinks on shapes
- Tooltips

**Verifiability:** HIGH — drawio verifier reads XML directly from .drawio file. All structural properties are inspectable.

---

### gedit (21 tasks) — HAS 16 PROPOSALS

**Already covered (existing tasks):**
- Bash script creation
- HTML file creation
- CSV editing
- Python class creation
- Log filter
- Find/replace
- Sort lines
- Line numbering
- SQL schema
- YAML k8s config
- Various file format creation

**Proposals cover:**
- Enable line numbers (settings)
- Word wrap + spell check
- Tab/spaces indent settings
- Plugin: embedded terminal
- Plugin: file browser
- And 11 more proposals

**Missing from proposals:**
- Keybindings customization
- Multiple window management
- Font size change via preferences
- Color scheme/theme change
- Auto-indent toggle
- Backup files setting

**Verifiability:** HIGH for content; MEDIUM for settings (gsettings-based).

---

### kdenlive (20 tasks) — HAS 15 PROPOSALS

**Already covered (existing tasks):**
- 4K vertical project
- 50fps fast action
- 720p five clips
- Audio/video mix
- Blur + invert stack
- Cinema 24fps dissolve
- Clips with luma transition
- Color correction stack
- Effect + render
- Multiple effects stack
- Multitrack effects
- New project + add clips
- PiP overlay glow render
- Project with effects
- Render 720p wipe
- SD project with transition
- Six-track project
- Square Instagram project
- Three-clip sequence
- Transition between clips

**Proposals cover:**
- Title clip text
- Speed change slow motion
- Audio track effects
- Keyframe zoom effect
- Color grade LUT
- And 10 more proposals

**Missing from proposals:**
- Proxy clip settings
- Project default profile change
- Subtitle/caption track
- Nested sequence
- Motion tracking

**Verifiability:** HIGH — kdenlive saves to XML files, verifier parses producers, tracks, effects directly.

---

### pcmanfm (20 tasks) — HAS 15 PROPOSALS

**Already covered (existing tasks):**
- Archive + reshape
- Bookmarks
- Bookmark + study dir
- Bulk rename with prefix
- Cleanup temp files
- Create project dir structure
- Deduplicate + organize
- Duplicate + rename
- Make executable
- JSON manifest + permissions
- Log rotation
- Multi-extension sort
- Nested archive creation
- Organize photos by date
- Change permissions
- Photo library by year
- Sort + organize
- Symlink creation
- Symlink to dotfile
- View mode list + sort

**Proposals cover:**
- Sort by size/date
- View mode toggle
- Show hidden files
- File type filter + organize
- Open with application
- And 10 more proposals

**Missing from proposals:**
- Network/remote mount management
- File tagging (custom metadata)
- Thumbnail size adjustments
- Toolbar customization

**Verifiability:** HIGH — pcmanfm verifier checks file existence, permissions, symlinks, bookmarks via filesystem.

---

### zoom (20 tasks)

**Already covered:**
- Accessibility (keyboard shortcuts, motion)
- Audio device swap
- Audio settings bundle
- Language German
- Recording path change
- Chat preferences
- Dark theme
- Disable autostart
- Disable mirror video
- Disable touchup appearance
- Enable HD video
- General meetings UI bundle
- Language Chinese + recording
- Multi-section hardening
- Mute mic on join
- Privacy lockdown
- Recording storage bundle
- Video off on join
- Video quality full bundle
- Virtual background setup

**Missing:**
- Background blur settings
- Closed captions/transcription settings
- Share screen quality settings
- Waiting room settings
- Reaction emoji settings
- Whiteboard settings
- Meeting reminder settings
- Combined audio+video+meetings workflow
- Bandwidth limits

**Verifiability:** HIGH — Zoom config stored in `/home/user/.config/zoomus.conf` INI file. All settings verifiable via key-value reads.

---

### shotcut (20 tasks) — NO PROPOSALS

**Already covered (existing tasks):**
- 720p single clip
- Add two clips
- Apply brightness filter
- Default profile
- Export 720p
- Export small
- Multi-track audio
- Set theme
- Three-clip sequence
- Two clips with luma
- v2: crop filter
- v2: default profile DV
- v2: default profile UHD 2160p
- v2: export audio AAC
- v2: five-clip
- v2: four-track layered
- v2: transition + fadein
- v2: two filters sepia
- v2: UHD 4K
- v2: vertical 9x16

**Missing:**
- Subtitles/captions track
- Audio normalization filter
- Speed/pitch adjustment
- Keyframe animation
- Color grading (white balance, contrast)
- Multiple audio tracks mixing
- Proxy editing settings
- Export presets (custom, web, mobile)
- Stabilization filter
- Properties panel editing (clip speed, in/out points)

**Verifiability:** HIGH — Shotcut saves MLT XML files, verifier parses producers, filters, tracks directly.

---

### firefox (20 tasks) — HAS PROPOSALS AND EVALUATED

**Already covered (existing tasks):**
- Bookmarks (multiple, three sites)
- Change download dir + bookmark
- Custom newtab + startup
- Download + bookmark
- Download multiple files
- Font zoom UI
- Form fill
- History multi-site
- httpbin endpoints
- Local bookmark three
- Local form submit
- Local HTML + history
- Local JS form
- Local JS stateful
- Local multisite
- Local table DOM
- Multi-tab
- Privacy hardening
- Set multiple preferences
- Wikipedia topic

**Has proposals/evaluated — primary gap:**
- Complex privacy settings combinations
- Extension management
- Sync settings
- PDF.js viewer interaction
- Developer tools integration
- Search engine customization

**Verifiability:** HIGH — firefox verifier reads profile (bookmarks SQLite, history, prefs.js).

---

### writer (libreoffice_writer prefix, 10 tasks)

**Already covered:**
- Course syllabus formatting
- Edit existing table data
- Employee directory table
- Find/replace cleanup
- Landscape page with bookmarks
- Meeting minutes formatting
- Multi-table inventory
- Product catalog tables
- Project status document
- Report restructure

**Missing (libreoffice_writer category):**
- Export to PDF
- Mail merge with CSV data
- Table of contents generation
- Track changes + accept/reject
- Comments/annotations
- Footnotes and endnotes
- Headers and footers
- Page numbering
- Paragraph/character styles
- Spell check language configuration
- AutoCorrect settings
- Page orientation and margins

**Verifiability:** HIGH for file content (parse-tables, heading checks), MEDIUM for settings (registrymodifications.xcu for prefs, ODT XML for page setup).

---

## Priority Action Plan

### Tier 1: Generate now (biggest gaps, clear verifiability)
1. **galculator** — scientific mode, paper mode, percentage tasks
2. **brave** — settings/preferences tasks
3. **chrome** — settings/preferences tasks
4. **zoom** — additional combined setting workflows

### Tier 2: Evaluate existing proposals, then finalize
5. **gedit** — evaluate 16 proposals, finalize best
6. **kdenlive** — evaluate 15 proposals, finalize best
7. **pcmanfm** — evaluate 15 proposals, finalize best

### Tier 3: Additional extension
8. **shotcut** — new proposals for filter/export/subtitle tasks
9. **writer (libreoffice_writer)** — PDF export, mail merge, TOC tasks
10. **drawio** — page management, export, libraries tasks
