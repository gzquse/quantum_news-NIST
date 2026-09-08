# NIST Post-Quantum Cryptography – History Map

_Auto-updated weekly. Last refresh: Sep 8, 2026. Every entry links to the original NIST page and document._

## Why this matters (the problem NIST set out to solve)

Today's internet security (RSA, elliptic-curve crypto) relies on math problems that a large quantum computer could solve quickly. Nobody has built one that big yet, but data encrypted today could be recorded and cracked later ('harvest now, decrypt later'). NIST's job was to pick new, quantum-safe algorithms and turn them into official U.S. standards that the whole world tends to adopt.

## What changed this week

No new NIST PQC announcements this week. Most recent item on record: **HAWK withdrawn from the additional-signatures race – 8 Round 3 candidates remain** (Jul 29, 2026).

## Where things stand right now

| Item | Status | Since | Link |
|---|---|---|---|
| FIPS 203 – ML-KEM (encryption / key exchange, from Kyber) | Final standard | Aug 13, 2024 | [NIST](https://csrc.nist.gov/pubs/fips/203/final) |
| FIPS 204 – ML-DSA (digital signatures, from Dilithium) | Final standard | Aug 13, 2024 | [NIST](https://csrc.nist.gov/pubs/fips/204/final) |
| FIPS 205 – SLH-DSA (backup signatures, from SPHINCS+) | Final standard | Aug 13, 2024 | [NIST](https://csrc.nist.gov/pubs/fips/205/final) |
| FIPS 206 – FN-DSA (compact signatures, from Falcon) | Selected 2022; standard still pending – NIST lists it as 'FIPS coming soon' | Jul 5, 2022 | [NIST](https://csrc.nist.gov/Projects/post-quantum-cryptography/post-quantum-cryptography-standardization/selected-algorithms) |
| HQC (backup encryption / KEM) | Selected March 2025; draft standard pending, final expected ~2027 | Mar 11, 2025 | [NIST](https://csrc.nist.gov/News/2025/hqc-announced-as-a-4th-round-selection) |
| NIST IR 8547 – transition timeline (2030 deprecate / 2035 disallow) | Draft only (Nov 2024); final not yet published | Nov 12, 2024 | [NIST](https://csrc.nist.gov/pubs/ir/8547/ipd) |
| SP 800-227 – KEM usage guidance | Final | Sep 18, 2025 | [NIST](https://csrc.nist.gov/pubs/sp/800/227/final) |
| SP 800-230 – extra SLH-DSA parameter sets | Draft; comments closed June 2026 | Apr 13, 2026 | [NIST](https://csrc.nist.gov/pubs/sp/800/230/ipd) |
| Additional signature schemes | Round 3 – 9 advanced May 2026, HAWK since withdrawn (8 remain); ~2 years of evaluation | Jul 29, 2026 | [NIST](https://csrc.nist.gov/projects/pqc-dig-sig/round-3-additional-signatures) |

## The full timeline

### 2015–2017 · Foundations: studying the problem and launching a public competition

#### Apr 2, 2015 – First NIST workshop on 'Cybersecurity in a Post-Quantum World'

NIST gathers researchers to ask: how worried should we be about quantum computers breaking encryption, and what should we do? This is the informal starting gun.

Links: [Workshop page](https://csrc.nist.gov/events/2015/workshop-on-cybersecurity-in-a-post-quantum-world)

#### Apr 28, 2016 – NIST IR 8105 – 'Report on Post-Quantum Cryptography'

NIST's first formal report. In plain terms it says: the threat is real enough that we should start replacing today's public-key crypto now, because swapping algorithms across the whole internet takes a decade or more.

Links: [Announcement](https://csrc.nist.gov/News/2016/NIST-Released-NISTIR-8105,-Report-on-Post-Quantum) · [Report (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2016/NIST.IR.8105.pdf)

#### Dec 20, 2016 – Official Call for Proposals – the PQC 'competition' opens

NIST invites cryptographers worldwide to submit candidate algorithms for two jobs: (1) key exchange / encryption (a 'KEM') and (2) digital signatures. NIST calls it a 'process', not a competition, because more than one winner is allowed.

Links: [Announcement](https://csrc.nist.gov/News/2016/Public-Key-Post-Quantum-Cryptographic-Algorithms) · [Call for Proposals (PDF)](https://csrc.nist.gov/CSRC/media/Projects/Post-Quantum-Cryptography/documents/call-for-proposals-final-dec-2016.pdf)

### 2017–2022 · The competition: 82 submissions whittled down over three rounds

#### Dec 21, 2017 – Round 1 begins – 69 complete submissions accepted (out of 82 received)

The field is announced. Over the next year, academics and NIST try to break each other's designs; several fall within weeks.

Links: [Round 1 submissions](https://csrc.nist.gov/Projects/post-quantum-cryptography/post-quantum-cryptography-standardization/round-1-submissions)

#### Apr 11, 2018 – First PQC Standardization Conference (Fort Lauderdale, FL)

Submitters present their algorithms in person; the community starts comparing speed, key sizes and security arguments side by side.

Links: [Workshops & timeline](https://csrc.nist.gov/Projects/post-quantum-cryptography/workshops-and-timeline)

#### Jan 30, 2019 – Round 2 – 26 candidates advance (NIST IR 8240)

NIST cuts the field from 69 to 26 and publishes a report explaining why each one stayed or went.

Links: [Announcement](https://csrc.nist.gov/News/2019/pqc-standardization-process-2nd-round-candidates) · [Status report IR 8240 (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2019/NIST.IR.8240.pdf)

#### Jul 22, 2020 – Round 3 – 7 finalists and 8 alternates (NIST IR 8309)

Finalists are the ones NIST thinks could be standardized soon; 'alternates' are promising but need more study. Lattice-based schemes (Kyber, Dilithium, Falcon, NTRU, SABER) dominate.

Links: [Announcement](https://csrc.nist.gov/News/2020/pqc-third-round-candidate-announcement) · [Status report IR 8309 (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8309.pdf)

### 2022–2024 · Winners chosen, drafts written, first standards published

#### Jul 5, 2022 – Winners announced: CRYSTALS-Kyber, CRYSTALS-Dilithium, Falcon, SPHINCS+ (NIST IR 8413)

After nearly six years, NIST picks one algorithm for encryption/key exchange (Kyber) and three for signatures (Dilithium as the main one, Falcon for when small signatures matter, SPHINCS+ as a differently-built backup). Four more encryption candidates (BIKE, Classic McEliece, HQC, SIKE) go into a 4th round as possible backups. SIKE was broken by researchers a month later and withdrew.

Links: [Announcement](https://csrc.nist.gov/News/2022/pqc-candidates-to-be-standardized-and-round-4) · [Status report IR 8413 (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2022/NIST.IR.8413-upd1.pdf) · [Selected algorithms](https://csrc.nist.gov/Projects/post-quantum-cryptography/post-quantum-cryptography-standardization/selected-algorithms)

#### Sep 6, 2022 – NIST asks for MORE signature algorithms (the 'additional signatures' track)

Two of the three chosen signature schemes use the same kind of math (structured lattices). NIST wants insurance in case that math is ever broken, plus schemes with very short signatures, so it opens a second call just for signatures.

Links: [Announcement](https://csrc.nist.gov/News/2022/request-additional-pqc-digital-signature-schemes) · [Call for proposals (PDF)](https://csrc.nist.gov/csrc/media/Projects/pqc-dig-sig/documents/call-for-proposals-dig-sig-sept-2022.pdf) · [Project page](https://csrc.nist.gov/projects/pqc-dig-sig)

#### Aug 24, 2023 – Draft standards FIPS 203, 204, 205 released for public comment

The winners get their official names: Kyber → ML-KEM (FIPS 203), Dilithium → ML-DSA (FIPS 204), SPHINCS+ → SLH-DSA (FIPS 205). Anyone can send comments until Nov 22, 2023. Falcon's standard (FIPS 206, 'FN-DSA') is promised later.

Links: [Announcement](https://csrc.nist.gov/News/2023/three-draft-fips-for-post-quantum-cryptography)

#### Aug 13, 2024 – ★ FIPS 203, 204, 205 become official U.S. standards

The big milestone. Secretary of Commerce approves the first three post-quantum standards. NIST's message: 'go ahead and start using these three' – don't wait. ML-KEM protects data in transit (think HTTPS), ML-DSA and SLH-DSA prove who signed something (software updates, certificates).

Links: [Announcement](https://csrc.nist.gov/News/2024/postquantum-cryptography-fips-approved) · [NIST press release (plain-English)](https://www.nist.gov/news-events/news/2024/08/nist-releases-first-3-finalized-post-quantum-encryption-standards) · [FIPS 203 ML-KEM (PDF)](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf) · [FIPS 204 ML-DSA (PDF)](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf) · [FIPS 205 SLH-DSA (PDF)](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.205.pdf)

### 2024–2026 · Filling the gaps: backup algorithms, transition plan, extra signatures

#### Jul 17, 2023 – Additional signatures Round 1 – 40 candidates accepted

The second signature contest starts with 40 entries built on a wider variety of math (codes, multivariate equations, isogenies, hash/MPC tricks).

Links: [Announcement](https://csrc.nist.gov/News/2023/additional-pqc-digital-signature-candidates) · [Round 1 candidates](https://csrc.nist.gov/Projects/pqc-dig-sig/round-1-additional-signatures)

#### Oct 25, 2024 – Additional signatures Round 2 – 14 candidates advance (NIST IR 8528)

The 40 extra signature candidates are cut to 14: CROSS, FAEST, HAWK, LESS, MAYO, Mirath, MQOM, PERK, QR-UOV, RYDE, SDitH, SNOVA, SQIsign, UOV.

Links: [Announcement](https://csrc.nist.gov/News/2024/pqc-digital-signature-second-round-announcement) · [Status report IR 8528](https://csrc.nist.gov/pubs/ir/8528/final) · [IR 8528 (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.IR.8528.pdf)

#### Nov 12, 2024 – Draft NIST IR 8547 – the transition timetable (still a draft)

The 'when do we have to switch?' document. Draft plan: today's 112-bit-strength RSA/ECC (e.g. RSA-2048, P-256) becomes 'deprecated' (discouraged) after 2030, and ALL quantum-vulnerable public-key crypto is 'disallowed' after 2035. Comments closed Jan 10, 2025; a final version has not been published as of this map.

Links: [Announcement](https://csrc.nist.gov/News/2024/draft-nist-ir-8547-is-available-for-comment) · [Publication page](https://csrc.nist.gov/pubs/ir/8547/ipd) · [Draft IR 8547 (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.IR.8547.ipd.pdf)

#### Jan 7, 2025 – Draft SP 800-227 – how to use KEMs safely

A how-to guide for engineers using ML-KEM and similar 'key encapsulation' tools correctly, including mixing them with today's crypto ('hybrid' mode). Comments until March 7, 2025; a NIST workshop on KEM guidance followed on Feb 25–26, 2025.

Links: [Announcement](https://csrc.nist.gov/News/2025/draft-sp-800-227-is-available-for-comment) · [KEM guidance workshop](https://csrc.nist.gov/Events/2025/workshop-on-guidance-for-kems)

#### Mar 11, 2025 – HQC chosen as the backup encryption algorithm (NIST IR 8545)

From the 4th round, NIST picks HQC as a second, differently-built KEM in case a flaw is ever found in ML-KEM's lattice math (HQC uses error-correcting codes instead). NIST said a draft standard would follow, with a final version in roughly two years (~2027). BIKE and Classic McEliece were not selected.

Links: [Announcement](https://csrc.nist.gov/News/2025/hqc-announced-as-a-4th-round-selection) · [Status report IR 8545](https://csrc.nist.gov/pubs/ir/8545/final) · [IR 8545 (PDF)](https://nvlpubs.nist.gov/nistpubs/ir/2025/NIST.IR.8545.pdf)

#### Sep 18, 2025 – SP 800-227 finalized – 'Recommendations for Key-Encapsulation Mechanisms'

The KEM how-to guide becomes final. Useful for anyone deciding how to plug ML-KEM into real products.

Links: [Announcement](https://csrc.nist.gov/News/2025/nist-publishes-sp-800-227) · [Publication page](https://csrc.nist.gov/pubs/sp/800/227/final) · [SP 800-227 (PDF)](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-227.pdf)

#### Sep 24, 2025 – Sixth PQC Standardization Conference (Gaithersburg, MD)

Three days of talks on the 14 extra signature candidates, HQC, and real-world migration lessons.

Links: [Conference page](https://csrc.nist.gov/Events/2025/6th-pqc-standardization-conference)

#### Apr 13, 2026 – Draft SP 800-230 – smaller, faster SLH-DSA variants for firmware/software signing

Adds six new SLH-DSA settings that make signatures smaller and faster to check, in exchange for a limit of about 16 million signatures per key (instead of effectively unlimited). Aimed at signing software and firmware. Comments closed June 12, 2026.

Links: [Announcement](https://csrc.nist.gov/News/2026/nist-releases-draft-sp-800-230) · [Publication page](https://csrc.nist.gov/pubs/sp/800/230/ipd) · [Draft SP 800-230 (PDF)](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-230.ipd.pdf)

#### Apr 17, 2026 – Draft SP 800-133 Rev. 3 – key generation guidance updated for PQC

NIST's general rulebook on how to generate cryptographic keys gets a revision that adds the new PQC algorithms, covers storing ML-KEM keys as compact 'seeds', and addresses hybrid classical+PQC setups. Comments closed June 16, 2026.

Links: [Announcement](https://csrc.nist.gov/News/2026/recommendation-for-cryptographic-key-generation) · [Publication page](https://csrc.nist.gov/pubs/sp/800/133/r3/ipd)

#### May 14, 2026 – Additional signatures Round 3 – 9 candidates advance (NIST IR 8610)

The extra-signature contest narrows from 14 to 9: FAEST, HAWK, MAYO, MQOM, QR-UOV, SDitH, SNOVA, SQIsign, UOV. Teams may submit 'tweaks'; NIST expects this round to take about two years, with a 7th PQC conference planned for late spring / early summer 2027.

Links: [Announcement](https://csrc.nist.gov/News/2026/nist-advances-9-candidates-to-the-3rd-round-of-pqc) · [Status report IR 8610](https://csrc.nist.gov/pubs/ir/8610/final) · [IR 8610 (PDF)](https://doi.org/10.6028/NIST.IR.8610) · [Round 3 candidates](https://csrc.nist.gov/projects/pqc-dig-sig/round-3-additional-signatures)

#### Jul 29, 2026 – HAWK withdrawn from the additional-signatures race – 8 Round 3 candidates remain

NIST's Round 3 page now notes that the HAWK team has withdrawn their lattice-based signature scheme from the process (NIST's page was updated July 29, 2026; NIST did not post a dated news item). That leaves eight candidates: FAEST, MAYO, MQOM, QR-UOV, SDitH, SNOVA, SQIsign and UOV – all built on non-lattice math, which is exactly the diversity NIST wanted from this track.

Links: [Round 3 candidates page (see HAWK note)](https://csrc.nist.gov/projects/pqc-dig-sig/round-3-additional-signatures)

## What NIST has said is coming next

These NIST pages do not exist yet; the weekly job checks them and will flag the moment one goes live.

- Draft FIPS 206 (FN-DSA / Falcon) published for comment – will appear at <https://csrc.nist.gov/pubs/fips/206/ipd>
- Final FIPS 206 (FN-DSA / Falcon) – will appear at <https://csrc.nist.gov/pubs/fips/206/final>
- Draft FIPS 207 (expected to be HQC) published for comment – will appear at <https://csrc.nist.gov/pubs/fips/207/ipd>
- Final FIPS 207 (HQC) – will appear at <https://csrc.nist.gov/pubs/fips/207/final>
- Final NIST IR 8547 transition timeline – will appear at <https://csrc.nist.gov/pubs/ir/8547/final>
- Final SP 800-230 (extra SLH-DSA parameter sets) – will appear at <https://csrc.nist.gov/pubs/sp/800/230/final>
- Final SP 800-133 Rev. 3 (key generation incl. PQC) – will appear at <https://csrc.nist.gov/pubs/sp/800/133/r3/final>
- 7th PQC Standardization Conference (planned spring/summer 2027) – will appear at <https://csrc.nist.gov/Events/2027/7th-pqc-standardization-conference>

## Plain-English glossary

- **PQC (post-quantum cryptography)** – Encryption and signature methods designed to stay secure even against a future large quantum computer.
- **KEM (key-encapsulation mechanism)** – A way for two computers to agree on a secret key over the open internet. It's the 'handshake' step before the actual encrypted conversation. ML-KEM and HQC are KEMs.
- **Digital signature** – A mathematical stamp proving who created a message or file and that it wasn't altered. Used in software updates and website certificates. ML-DSA, SLH-DSA, FN-DSA are signature schemes.
- **FIPS** – Federal Information Processing Standard – an official U.S. government standard. Once something is a FIPS, U.S. agencies (and many vendors worldwide) are expected to use it.
- **SP 800-xxx** – NIST Special Publication – detailed guidance on how to use the standards properly.
- **NIST IR** – NIST Internal/Interagency Report – explains NIST's reasoning, e.g., why candidates were kept or dropped.
- **IPD** – Initial Public Draft – a first draft open for public comment; not yet official.
- **Lattice-based** – The family of math behind ML-KEM, ML-DSA and FN-DSA. Fast and well-studied, but NIST wants backups built on different math just in case.
- **Deprecated vs. disallowed** – Deprecated = still allowed but discouraged and being phased out. Disallowed = no longer permitted for federal use.
- **Harvest now, decrypt later** – The fear that adversaries record encrypted traffic today and decrypt it years from now once quantum computers exist. This is why the switch can't wait.
- **Hybrid** – Using a traditional algorithm and a PQC algorithm together, so you're safe as long as at least one holds up.

---
_Sources: NIST CSRC PQC project <https://csrc.nist.gov/projects/post-quantum-cryptography> and its news pages. Generated by `nist_pqc_weekly.py`._
