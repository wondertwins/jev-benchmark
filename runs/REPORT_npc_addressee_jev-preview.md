# Jev addressee detection for speech-to-text NPC dialogue — model `jev-preview`

79 hand-labeled utterances in a fantasy village with 2 to 5 NPCs within earshot. For each NPC, one Noul asks whether the player is speaking to them. Ground truth is my labeling; 4 arguable items are excluded from strict metrics and listed separately. Baseline = fuzzy name/role matching + group words + facing/last-speaker fallback.

## Per-NPC 'is being spoken to' decisions

| transcript variant | decisions | Jev F1 | Jev precision | Jev recall | baseline F1 | Jev exact-set acc | baseline exact-set acc | Jev Brier |
|---|---|---|---|---|---|---|---|---|
| clean | 237 | **0.962** | 1.0 | 0.926 | 0.82 | **0.92** | 0.64 | 0.021 |
| stt_misheard | 237 | **0.933** | 1.0 | 0.874 | 0.786 | **0.853** | 0.613 | 0.041 |

Exact-set = every NPC in the scene classified correctly for that utterance.

## Other judgments (same request)

| variant | nobody Noul F1 | group Noul F1 | intent accuracy (7 classes) | primary-addressee Choice acc (single-addressee items) | Choice says 'nobody' when nobody | mean input tokens |
|---|---|---|---|---|---|---|
| clean | 0.875 | 0.714 | 0.911 | 0.981 | 1 | 1667 |
| stt_misheard | 0.7 | 0.714 | 0.899 | 0.925 | 1 | 1681 |

## By category (exact-set accuracy, Jev vs baseline)

| category | n | clean Jev / base | stt_misheard Jev / base |
|---|---|---|---|
| continuation | 4 | 1 / 1 | 1 / 1 |
| continuation_with_mention | 1 | 1 / 0 | 1 / 0 |
| description_address | 1 | 1 / 0 | 1 / 0 |
| description_address_facing | 1 | 1 / 1 | 1 / 1 |
| direct_multi | 5 | 1 / 0.6 | 1 / 0.6 |
| direct_multi_attention_shift | 3 | 0.67 / 0.67 | 0.67 / 0 |
| direct_multi_with_mentions | 1 | 1 / 1 | 0 / 0 |
| direct_single | 8 | 1 / 0.75 | 1 / 0.62 |
| direct_single_with_mentions | 1 | 1 / 0 | 1 / 0 |
| facing_deixis | 3 | 1 / 1 | 1 / 1 |
| facing_deixis_role_mentioned | 1 | 1 / 0 | 1 / 0 |
| group_all | 5 | 1 / 1 | 1 / 1 |
| group_then_single | 1 | 0 / 1 | 0 / 1 |
| insult | 1 | 1 / 0 | 1 / 0 |
| mention_absent | 2 | 1 / 1 | 0.5 / 0.5 |
| mention_only | 9 | 0.89 / 0 | 0.78 / 0.22 |
| mention_only_relay | 1 | 1 / 0 | 1 / 0 |
| mention_only_topic_needs_context | 4 | 0.25 / 0 | 0.25 / 0 |
| mention_then_address | 1 | 1 / 1 | 1 / 1 |
| mid_sentence_vocative | 3 | 1 / 0.67 | 1 / 1 |
| offstage_addressee | 1 | 1 / 1 | 1 / 1 |
| out_of_game | 2 | 1 / 1 | 1 / 1 |
| reported_speech | 3 | 1 / 0.33 | 0.33 / 0.67 |
| role_address | 5 | 1 / 1 | 1 / 1 |
| role_address_plural_one_present | 1 | 1 / 1 | 1 / 1 |
| role_synonym | 1 | 1 / 1 | 1 / 1 |
| self_talk | 4 | 1 / 1 | 1 / 1 |
| threat | 2 | 1 / 1 | 1 / 0.5 |

## Arguable items (clean variant), excluded from strict metrics

- "Whoever owns this cart, move it!"  truth {'Hanna': True, 'Jeff': True, 'Anna': True, 'Marcus': True, 'Elara': True}  → Jev {'Hanna': 0.09, 'Jeff': 0.13, 'Anna': 0.22, 'Marcus': 0.1, 'Elara': 0.06}
- "Everyone except Jeff, come with me."  truth {'Hanna': True, 'Jeff': True, 'Anna': True}  → Jev {'Hanna': 0.94, 'Jeff': 0.11, 'Anna': 0.94}
- "I'm not talking to you, Jeff. Hanna, another round."  truth {'Hanna': True, 'Jeff': True, 'Anna': False}  → Jev {'Hanna': 0.96, 'Jeff': 0.25, 'Anna': 0.05}
- "Elara... no wait, Anna, you're the merchant, right?"  truth {'Anna': True, 'Elara': False}  → Jev {'Anna': 0.88, 'Elara': 0.07}