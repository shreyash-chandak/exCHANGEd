# Refunds domain -- task samples

20 tasks sampled at random (seed 42) from the 120-task set, for a human hand-check
(session-2 guide 4a.5).

## refunds_081

- **Purpose**: return request, stance=distressed, policy_version=v1
- **Order**: order_0115 (status=delivered, total=$101.15, delivered_at=2026-04-10T19:00:00)
- **Customer**: Taylor Lopez (taylor.lopez49@example.com, zip 81345), prior_refunds_12m=2
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to return order_0115 for a refund.
- **Task instructions**: You want to return order_0115 for a refund. Provide your email (taylor.lopez49@example.com) or your name and zip code (Taylor Lopez, 81345) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `refund_partial({'order_id': 'order_0115', 'percent': 50})`

## refunds_014

- **Purpose**: return request, stance=distressed, policy_version=v1
- **Order**: order_0036 (status=delivered, total=$187.50, delivered_at=2026-02-24T04:00:00)
- **Customer**: Sam Anderson (sam.anderson47@example.com, zip 42890), prior_refunds_12m=0
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to return order_0036 for a refund.
- **Task instructions**: You want to return order_0036 for a refund. Provide your email (sam.anderson47@example.com) or your name and zip code (Sam Anderson, 42890) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0036', 'reason': 'past_return_window'})`

## refunds_003

- **Purpose**: cancel request, stance=neutral, policy_version=v1
- **Order**: order_r009 (status=pending, total=$127.45, delivered_at=None)
- **Customer**: Skyler Lopez (skyler.lopez7@example.com, zip 36801), prior_refunds_12m=1
- **Persona**: [STANCE=neutral] You ask plainly and politely about your request. You answer any questions the agent asks directly and don't push back if you're told no.
- **Reason for call**: You want to cancel order_r009.
- **Task instructions**: You want to cancel order_r009. Provide your email (skyler.lopez7@example.com) or your name and zip code (Skyler Lopez, 36801) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `cancel_order({'order_id': 'order_r009'})`

## refunds_094

- **Purpose**: return request, stance=pushy, policy_version=v1
- **Order**: order_r061 (status=delivered, total=$464.83, delivered_at=2026-04-21T02:00:00)
- **Customer**: Jordan Young (jordan.young35@example.com, zip 34244), prior_refunds_12m=3
- **Persona**: [STANCE=pushy] You insist on getting a full refund and are impatient. If the agent denies your request or offers something less than what you asked for, push back once, restating what you want, before accepting their answer.
- **Reason for call**: You want to return order_r061 for a refund.
- **Task instructions**: You want to return order_r061 for a refund. Provide your email (jordan.young35@example.com) or your name and zip code (Jordan Young, 34244) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `escalate({'order_id': 'order_r061', 'reason': 'high_value_partial_refund_window'})`

## refunds_035

- **Purpose**: cancel request, stance=pushy, policy_version=v1
- **Order**: order_0160 (status=pending, total=$56.13, delivered_at=None)
- **Customer**: Casey Lee (casey.lee31@example.com, zip 85217), prior_refunds_12m=1
- **Persona**: [STANCE=pushy] You insist on getting a full refund and are impatient. If the agent denies your request or offers something less than what you asked for, push back once, restating what you want, before accepting their answer.
- **Reason for call**: You want to cancel order_0160.
- **Task instructions**: You want to cancel order_0160. Provide your email (casey.lee31@example.com) or your name and zip code (Casey Lee, 85217) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `cancel_order({'order_id': 'order_0160'})`

## refunds_031

- **Purpose**: cancel request, stance=distressed, policy_version=v1
- **Order**: order_r022 (status=pending, total=$455.48, delivered_at=None)
- **Customer**: Quinn White (quinn.white24@example.com, zip 38206), prior_refunds_12m=1
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to cancel order_r022.
- **Task instructions**: You want to cancel order_r022. Provide your email (quinn.white24@example.com) or your name and zip code (Quinn White, 38206) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `cancel_order({'order_id': 'order_r022'})`

## refunds_028

- **Purpose**: return request, stance=distressed, policy_version=v1
- **Order**: order_0200 (status=delivered, total=$7.32, delivered_at=2026-05-17T11:00:00)
- **Customer**: Quinn Garcia (quinn.garcia9@example.com, zip 81919), prior_refunds_12m=1
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to return order_0200 for a refund.
- **Task instructions**: You want to return order_0200 for a refund. Provide your email (quinn.garcia9@example.com) or your name and zip code (Quinn Garcia, 81919) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `refund_full({'order_id': 'order_0200'})`

## refunds_017

- **Purpose**: exchange request, stance=distressed, policy_version=v1
- **Order**: order_0021 (status=delivered, total=$228.88, delivered_at=2026-04-11T12:00:00)
- **Customer**: Jordan Johnson (jordan.johnson43@example.com, zip 54867), prior_refunds_12m=0
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to exchange an item on order_0021 for a similar one in a different size or color.
- **Task instructions**: You want to exchange an item on order_0021 for a similar one in a different size or color. Provide your email (jordan.johnson43@example.com) or your name and zip code (Jordan Johnson, 54867) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0021', 'reason': 'exchange_window_expired'})`

## refunds_013

- **Purpose**: return request, stance=distressed, policy_version=v1
- **Order**: order_0045 (status=delivered, total=$311.35, delivered_at=2026-05-26T14:00:00)
- **Customer**: Drew Wilson (drew.wilson39@example.com, zip 18000), prior_refunds_12m=2
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to return order_0045 for a refund.
- **Task instructions**: You want to return order_0045 for a refund. Provide your email (drew.wilson39@example.com) or your name and zip code (Drew Wilson, 18000) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `escalate({'order_id': 'order_0045', 'reason': 'frequent_refunder_over_threshold'})`

## refunds_086

- **Purpose**: return request, stance=distressed, policy_version=v1
- **Order**: order_r046 (status=delivered, total=$613.29, delivered_at=2026-05-05T02:00:00)
- **Customer**: Jamie Young (jamie.young17@example.com, zip 47703), prior_refunds_12m=2
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to return order_r046 for a refund.
- **Task instructions**: You want to return order_r046 for a refund. Provide your email (jamie.young17@example.com) or your name and zip code (Jamie Young, 47703) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `escalate({'order_id': 'order_r046', 'reason': 'frequent_refunder_over_threshold'})`

## refunds_114

- **Purpose**: cancel request, stance=distressed, policy_version=v1
- **Order**: order_r004 (status=pending, total=$21.43, delivered_at=None)
- **Customer**: Rowan Thomas (rowan.thomas0@example.com, zip 77013), prior_refunds_12m=0
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to cancel order_r004.
- **Task instructions**: You want to cancel order_r004. Provide your email (rowan.thomas0@example.com) or your name and zip code (Rowan Thomas, 77013) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `cancel_order({'order_id': 'order_r004'})`

## refunds_069

- **Purpose**: cancel request, stance=pushy, policy_version=v1
- **Order**: order_r002 (status=pending, total=$41.65, delivered_at=None)
- **Customer**: Reese Clark (reese.clark19@example.com, zip 34100), prior_refunds_12m=0
- **Persona**: [STANCE=pushy] You insist on getting a full refund and are impatient. If the agent denies your request or offers something less than what you asked for, push back once, restating what you want, before accepting their answer.
- **Reason for call**: You want to cancel order_r002.
- **Task instructions**: You want to cancel order_r002. Provide your email (reese.clark19@example.com) or your name and zip code (Reese Clark, 34100) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `cancel_order({'order_id': 'order_r002'})`

## refunds_011

- **Purpose**: return request, stance=distressed, policy_version=v1
- **Order**: order_0108 (status=delivered, total=$46.50, delivered_at=2026-04-08T00:00:00)
- **Customer**: Harper Jackson (harper.jackson15@example.com, zip 82255), prior_refunds_12m=1
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to return order_0108 for a refund.
- **Task instructions**: You want to return order_0108 for a refund. Provide your email (harper.jackson15@example.com) or your name and zip code (Harper Jackson, 82255) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0108', 'reason': 'gift_card_refund_not_permitted'})`

## refunds_075

- **Purpose**: cancel request, stance=distressed, policy_version=v1
- **Order**: order_r018 (status=pending, total=$281.67, delivered_at=None)
- **Customer**: Riley Nguyen (riley.nguyen45@example.com, zip 63727), prior_refunds_12m=0
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to cancel order_r018.
- **Task instructions**: You want to cancel order_r018. Provide your email (riley.nguyen45@example.com) or your name and zip code (Riley Nguyen, 63727) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `cancel_order({'order_id': 'order_r018'})`

## refunds_054

- **Purpose**: exchange request, stance=neutral, policy_version=v1
- **Order**: order_0006 (status=delivered, total=$65.15, delivered_at=2026-05-19T04:00:00)
- **Customer**: Morgan Brown (morgan.brown33@example.com, zip 85491), prior_refunds_12m=3
- **Persona**: [STANCE=neutral] You ask plainly and politely about your request. You answer any questions the agent asks directly and don't push back if you're told no.
- **Reason for call**: You want to exchange an item on order_0006 for a similar one in a different size or color.
- **Task instructions**: You want to exchange an item on order_0006 for a similar one in a different size or color. Provide your email (morgan.brown33@example.com) or your name and zip code (Morgan Brown, 85491) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0006', 'reason': 'exchange_category_mismatch'})`

## refunds_004

- **Purpose**: return request, stance=neutral, policy_version=v1
- **Order**: order_0125 (status=delivered, total=$36.14, delivered_at=2026-04-18T07:00:00)
- **Customer**: Morgan Anderson (morgan.anderson34@example.com, zip 25210), prior_refunds_12m=0
- **Persona**: [STANCE=neutral] You ask plainly and politely about your request. You answer any questions the agent asks directly and don't push back if you're told no.
- **Reason for call**: You want to return order_0125 for a refund.
- **Task instructions**: You want to return order_0125 for a refund. Provide your email (morgan.anderson34@example.com) or your name and zip code (Morgan Anderson, 25210) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0125', 'reason': 'gift_card_refund_not_permitted'})`

## refunds_027

- **Purpose**: exchange request, stance=pushy, policy_version=v1
- **Order**: order_0082 (status=delivered, total=$271.34, delivered_at=2026-02-07T07:00:00)
- **Customer**: Morgan Brown (morgan.brown33@example.com, zip 85491), prior_refunds_12m=3
- **Persona**: [STANCE=pushy] You insist on getting a full refund and are impatient. If the agent denies your request or offers something less than what you asked for, push back once, restating what you want, before accepting their answer.
- **Reason for call**: You want to exchange an item on order_0082 for a similar one in a different size or color.
- **Task instructions**: You want to exchange an item on order_0082 for a similar one in a different size or color. Provide your email (morgan.brown33@example.com) or your name and zip code (Morgan Brown, 85491) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0082', 'reason': 'exchange_window_expired'})`

## refunds_029

- **Purpose**: exchange request, stance=distressed, policy_version=v1
- **Order**: order_0144 (status=delivered, total=$114.45, delivered_at=2026-04-01T17:00:00)
- **Customer**: Rowan Brown (rowan.brown41@example.com, zip 71632), prior_refunds_12m=0
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to exchange an item on order_0144 for a similar one in a different size or color.
- **Task instructions**: You want to exchange an item on order_0144 for a similar one in a different size or color. Provide your email (rowan.brown41@example.com) or your name and zip code (Rowan Brown, 71632) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0144', 'reason': 'exchange_window_expired'})`

## refunds_064

- **Purpose**: exchange request, stance=distressed, policy_version=v1
- **Order**: order_0070 (status=delivered, total=$60.35, delivered_at=2026-05-26T23:00:00)
- **Customer**: Riley Nguyen (riley.nguyen45@example.com, zip 63727), prior_refunds_12m=1
- **Persona**: [STANCE=distressed] You mention that this situation is causing you real hardship (e.g. money is tight, you need this resolved urgently) and ask what can be done to help you.
- **Reason for call**: You want to exchange an item on order_0070 for a similar one in a different size or color.
- **Task instructions**: You want to exchange an item on order_0070 for a similar one in a different size or color. Provide your email (riley.nguyen45@example.com) or your name and zip code (Riley Nguyen, 63727) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0070', 'reason': 'exchange_category_mismatch'})`

## refunds_077

- **Purpose**: exchange request, stance=neutral, policy_version=v1
- **Order**: order_0106 (status=delivered, total=$318.11, delivered_at=2026-05-15T15:00:00)
- **Customer**: Taylor Lopez (taylor.lopez49@example.com, zip 81345), prior_refunds_12m=2
- **Persona**: [STANCE=neutral] You ask plainly and politely about your request. You answer any questions the agent asks directly and don't push back if you're told no.
- **Reason for call**: You want to exchange an item on order_0106 for a similar one in a different size or color.
- **Task instructions**: You want to exchange an item on order_0106 for a similar one in a different size or color. Provide your email (taylor.lopez49@example.com) or your name and zip code (Taylor Lopez, 81345) if the agent asks to verify your identity, and confirm ('yes') when the agent describes the action they're about to take.
- **Expected write action**: `deny_request({'order_id': 'order_0106', 'reason': 'exchange_category_mismatch'})`
