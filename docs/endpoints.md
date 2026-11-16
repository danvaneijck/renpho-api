# Renpho cloud API endpoints

This page records what is known about the Renpho cloud API that `renpho-api`
talks to. It is unofficial, and Renpho can change any of it without notice.

It comes from two sources:

- **The Renpho Health Android app, version 7.11.6** (the Google Play build,
  released November 2026). The APK's signature was verified against Renpho's
  Play signing certificate, then decompiled to list every endpoint the app
  declares, and the call sites were read for request payloads.
- **Live checks on one account in November 2026.** These were read-only calls
  that confirmed which endpoints answer, and with what shape. That account had
  only scale data (no body-composition, girth, goal or third-party records), so
  for those endpoints only the container shape was confirmed.

## How requests work

- **Transport.** `POST https://cloud.renpho.com/<path>` with a JSON body.
- **Encryption.** Request bodies are `{"encryptData": base64(AES-128-ECB(json))}`
  with PKCS7 padding. Responses are `{"code", "msg" or "message", "data"}`, where
  `data` is encrypted the same way. Success is `code` 101 (0, 200 and 20000 also
  appear). The key is `ENCRYPTION_KEY` in [`renpho/constants.py`](../renpho/constants.py).
- **Key selection.** The server picks the decryption key from the `appVersion`
  header. The bundled key is accepted for versions below 8.0.0. With no header,
  or 8.0.0 and above, the server answers -114. The app builds its key at runtime
  in native code (`libnative-lib.so`) and chooses it by build environment, never
  by app version, so the 8.0.0 cutoff is enforced server-side.
- **Headers.** The app sends these on every request: `token`, `userId`,
  `appVersion`, `platform` (`android`), `language`, `languageCode`,
  `systemVersion`, `phone`, `area`, `userArea`, `timeZone` (a whole-hour offset
  such as `+2` or `-5`), `zoneId` (an IANA name), `devId` and `Content-Type`.
  The library sends only `appVersion` and `platform`, adds `token` and `userId`
  once logged in, and adds `timeZone` where an endpoint requires it.
- **Sessions.** An account has one active session at a time. Any login, on any
  platform, ends every other session; this was checked with an Android and a web
  login. Tokens are JWTs valid for 90 days.

| Code | Meaning |
| --- | --- |
| 101 | Success |
| 104, 20001 | Wrong email or password |
| 106 | Email not registered |
| 401, 403 | Session invalid: expired, or replaced by another login (403 arrives inside an HTTP 200 body) |
| 429 | Rate limited |
| 1003 | "unknown exception", usually a payload the endpoint doesn't accept |
| -113 | Body not wrapped in `encryptData` |
| -114 | Decryption failed: `appVersion` missing, or 8.0.0 or later |

## Endpoints used by renpho-api

| Path | Library method | Request (decrypted) | Notes |
| --- | --- | --- | --- |
| `renpho-aggregation/user/login` | `login()` | `{"questionnaire": {}, "login": {"email", "password", "areaCode", "appRevision", "cellphoneType", "systemType", "platform"}, "bindingList": {"deviceTypes": LOGIN_DEVICE_TYPES}}` | The response holds `login` (the profile, including `token` and `id`) and `bindingList` (`bluetooth` and `wifi` device lists). Devices are listed only when the app's five-digit device-type codes are sent. |
| `renpho-aggregation/device/count` | `get_device_info()` | empty | Not used by the 7.11.6 app, but still answers. Has no `compositionScale` list. |
| `renpho-aggregation/device/countV2` | `get_data_counts()` | `{}` or `{"names": ["scale", "compositionScale"]}` | Per-table counts for the legacy (`scale`) and body-composition (`compositionScale`) stores, plus totals for girth, rope, treadmill, steps and goals. `compositionScale` is included only when asked for by name. |
| `RenphoHealth/scale/countAll` | `get_measurement_count()` | `{}` | `[{"userId", "count"}]` for the logged-in user. |
| `RenphoHealth/scale/queryAllMeasureDataList` | `get_measurements()` | `{"pageNum", "pageSize", "userIds": ["<id>"], "tableName"}` | Legacy store. The server returns only rows for the `userIds` asked for. The app sends `pageSize` as a string and `userIds` as a JSON-encoded string; the server also accepts a number and an array. |
| `RenphoHealth/scale/queryBodyCompositionMeasureData` | `get_body_composition_measurements()` | same as above, `userIds` as an array | Body-composition store. In the app's model, 8-electrode records include segmental fat and muscle (`la`, `ra`, `ll`, `rl`, `t`) and the `z20`/`z100` impedances. Not yet seen live. |
| `RenphoHealth/centerUser/queryFamilyMemberList` | `get_family_members()` | empty | The profiles under the account. The logged-in user isn't included. |
| `RenphoHealth/renpho/girth/queryAllGirthsDataList` | `get_girth_measurements()` | `{"pageNum", "pageSize"}` | Smart tape measure records. |
| `RenphoHealth/renpho/girth/uploadGirthsDataV2` | `upload_girth_measurements()` | an array of girth records | **Write.** Needs the fuller header set, including `timeZone` and `zoneId`. |
| `RenphoHealth/app/sync/getTokenTime` | `get_token_info()` | `{}` | `{"issAt", "expAt", "userId"}` in milliseconds. |
| `RenphoHealth/app/friend/friendsList` | `get_friends()` | `{"userId", "pageNum", "pageSize"}` | The friend endpoints come from a React Native bundle the app downloads at runtime, so they don't appear in the APK. Payloads follow [#14](https://github.com/danvaneijck/renpho-api/issues/14). |
| `RenphoHealth/app/friend/measure/has` | `get_friend_measure_days()` | `{"rhFriendIds", "timeZone"}` | Needs the `timeZone` header. |
| `RenphoHealth/app/friend/measure/model` | `get_friend_summary()` | `{"rhFriendId", "param"}` | |
| `RenphoHealth/app/friend/measure/trendV2` | `get_friend_trend()` | `{"rhFriendId", "timeZone", "param", "sourceDataType", "timeType", "endTime"}` | Needs the `timeZone` header. Returns one point per day for one parameter. |

### Experimental

These answer with code 101 on a live account, but that account had no records
of these kinds, so the record fields are unconfirmed.

| Path | Library method | Request | Response |
| --- | --- | --- | --- |
| `RenphoHealth/va/scale/getDualModeMeasurementByMac` | `get_unassigned_measurements()` | `{"userId": <int>, "pageSize": 20, "unknown": true, "getAll": 0}` | A page: `{"total", "list": [{"measurements", "unknownMeasurements"}], ...}` |
| `RenphoHealth/scale/queryThirdPartyMeasureData` | `get_third_party_measurements()` | `{"userId": <int>, "pageSize": "100", "pageNum": <n>}` | A list of measurement records |
| `RenphoHealth/scale/getThirdPartyDatasource` | `get_third_party_sources()` | `{"userId": <int>}` | `[{"id", "userId", "type", "date", "createTime"}]` (from the app's model) |
| `RenphoHealth/scale/queryGoalRecordsV2` | `get_goals()["scale"]` | `{}` | A list of goal records |
| `RenphoHealth/renpho/girth/queryGirthsGoals` | `get_goals()["girth"]` | `{}` | `[{"userId", "goalsList": [...]}]`, one entry per profile |

## Verified, not used by the library

| Path | Request | Response |
| --- | --- | --- |
| `RenphoHealth/scale/getUserIdMappingTableNames` | empty | `[{"tableName", "count", "userIds"}]`, the same as `device/count`'s `scale` list |
| `RenphoHealth/scale/bodyCompositionScaleCount` | `{}` | `{"goalCount", "measurementsInfoCountList": [{"tableName", "count", "userIds"}]}` |
| `RenphoHealth/scale/queryGoalRecords` | `{"pageNum", "pageSize"}` | `{"pageNum", "pageSize", "total", "content": [...]}` |
| `RenphoHealth/scale/countGoalRecord` | `{}` | a list of integers (their meaning is unclear) |
| `RenphoHealth/centerUser/queryFamilyMemberListV2` | `{"pageNum": 1, "pageSize": 100}` | the same profiles as V1, paged |
| `RenphoHealth/centerUser/countFamilyMember` | `{}` | `{"count"}` |
| `RenphoHealth/centerUser/getTimeStamp` | `{}` | `{"timestamp"}`, the server time |

## Known not to work

| Path | What happened |
| --- | --- |
| `RenphoHealth/healthManage/dailyCalories` | 1003 for every date. It isn't in the 7.11.6 app; it came from third-party code. |
| `RenphoHealth/scale/queryGoalRecord` | 1003 with `{}` |
| `RenphoHealth/centerUser/deviceInfo/v2` | 1003 with `{}` |
| `renpho-aggregation/device/bindingList` | HTTP 500 with `{}`. The request payload is unknown, because no Java code calls it. Devices come back in the login response instead. |

## Notable write endpoints

These are not called by the library. Writes are permanent, and some can only be
undone in the app.

| Path | Request (from the app) |
| --- | --- |
| `RenphoHealth/scale/uploadMeasureData` | An array of measurement records. [renpho-history-import](https://github.com/dchapman992000/renpho-history-import) sends batches of up to 10, with `timeZone` and `zoneId` headers. |
| `RenphoHealth/scale/v1.0/deleteMeasureData` | `[{"id", "userId"}]` |
| `RenphoHealth/scale/createMeasureRemark/` | `{"id": "<server id>", "extraField": "<note>", "subUserId"}`, where `subUserId` is sent only for a family member's row |
| `RenphoHealth/scale/uploadOfflineMeasureData` | An array of raw weigh-ins (`weight`, `resistance`, `secResistance`, `mac`, `timestamp`, ...). The server then assigns them to profiles. |
| `RenphoHealth/app/friend/approveOrReject` | `{"rhFriendId", "agreeOrNot", "id"}` |
| `RenphoHealth/centerUser/logoutUser` | No body. Ends the session on the server. |

## Full catalogue

Every endpoint the 7.11.6 app declares, grouped by service. A few details:

- **Kind** (read, write or account) is guessed from the endpoint's name and the
  app's method name.
- **Status** marks the endpoints described above.
- **Missing paths.** Paths the app builds at runtime and endpoints in its React
  Native bundles (such as the friend measurement endpoints) are not listed.
- **Other devices.** Treadmill, smart ring, blood pressure and food scale
  services are included for completeness. None of them has been tried.

<!-- generated from the decompiled app: 366 distinct paths -->

<details>
<summary><code>renpho-aggregation/</code> — 4 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-aggregation/getCalories` | POST | `getCaloriesDetail` | read |  |
| `renpho-aggregation/getCaloriesAndIntake` | POST | `getCaloriesAndIntake` | read |  |
| `renpho-aggregation/getCardV2` | POST | `getUserCard` | read |  |
| `renpho-aggregation/getDistances` | POST | `getDistanceDetail` | read |  |

</details>

<details>
<summary><code>renpho-aggregation/device/</code> — 4 endpoints (2 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-aggregation/device/binding` | — | — | write |  |
| `renpho-aggregation/device/bindingList` | POST | `getUserBindingDeviceList` | write | ❌ HTTP 500 with {} |
| `renpho-aggregation/device/countV2` | POST | `getCombineDataDataCount`, `getDeviceDataCount` | read | ✅ used |
| `renpho-aggregation/device/unbind` | POST | `suUnbindingDevice` | write |  |

</details>

<details>
<summary><code>renpho-aggregation/user/</code> — 3 endpoints (1 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-aggregation/user/authCodeCheck` | POST | `authCodeCheck1` | account |  |
| `renpho-aggregation/user/login` | POST | `login1` | account | ✅ used |
| `renpho-aggregation/user/thirdLogin` | POST | `loginThird` | account |  |

</details>

<details>
<summary><code>RenphoHealth/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/isFirst` | POST | `getIsFirstRemind` | read |  |

</details>

<details>
<summary><code>RenphoHealth/activity/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/activity/getActivityList` | POST | `requestPromotion` | read |  |
| `RenphoHealth/activity/participationActivity` | POST | `commitPromotion` | write |  |

</details>

<details>
<summary><code>RenphoHealth/app/</code> — 22 endpoints (1 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/app/friend/approveOrReject` | POST | `approveOrRejectFriend` | write |  |
| `RenphoHealth/app/guidance/select` | POST | `guideSelect` | read |  |
| `RenphoHealth/app/message/del` | POST | `deleteMsg` | write |  |
| `RenphoHealth/app/message/getNotificationUserMessage` | POST | `getAcSysMsg` | read |  |
| `RenphoHealth/app/message/markRead` | POST | `setMessageReading`, `setMsgReading` | write |  |
| `RenphoHealth/app/message/v5.0/listAllPerUser` | POST | `getMessageList` | read |  |
| `RenphoHealth/app/music/list` | POST | `getDeviceBackgroundMusic` | read |  |
| `RenphoHealth/app/notification/deleteMessage` | POST | `deleteMessage` | write |  |
| `RenphoHealth/app/notification/listDetails` | POST | `getFriendMessageList` | read |  |
| `RenphoHealth/app/notification/listNew` | — | — | read |  |
| `RenphoHealth/app/notification/messageCounts` | POST | `getMessageCounts1`, `suGetMessageCounts` | read |  |
| `RenphoHealth/app/notification/setIsRead` | POST | `setMessageIsRead` | write |  |
| `RenphoHealth/app/popup/getAppPopup` | POST | `getAppPopup` | read |  |
| `RenphoHealth/app/satisfaction/select` | POST | `satisfactionSelect` | read |  |
| `RenphoHealth/app/satisfaction/sub` | POST | `satisfactionSub` | write |  |
| `RenphoHealth/app/sync/action` | POST | `syncData` | ? |  |
| `RenphoHealth/app/sync/getTokenTime` | POST | `getSyncTokenTime` | read | ✅ used |
| `RenphoHealth/app/sync/isHidden` | POST | `isHidden` | read |  |
| `RenphoHealth/app/sync/prepare` | POST | `checkSyncDataPrepare` | read |  |
| `RenphoHealth/app/sync/sync` | POST | `sync` | ? |  |
| `RenphoHealth/app/tab/config/getTab` | POST | `getHomeTab` | read |  |
| `RenphoHealth/app/tab/config/getTab/v2` | POST | `getHomeTabV2` | read |  |

</details>

<details>
<summary><code>RenphoHealth/askPraise/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/askPraise/selectAskPraise` | POST | `selectAskPraise` | read |  |
| `RenphoHealth/askPraise/uploadAskPraise` | POST | `uploadAskPraise` | write |  |

</details>

<details>
<summary><code>RenphoHealth/background/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/background/getDeviceService` | POST | `getDeviceService` | read |  |

</details>

<details>
<summary><code>RenphoHealth/bluetooth/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/bluetooth/error` | POST | `getDetectErrorMsg` | read |  |
| `RenphoHealth/bluetooth/errorCode` | POST | `uploadErrorCode` | write |  |

</details>

<details>
<summary><code>RenphoHealth/card/</code> — 6 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/card/questionnaire/renphoNewUser` | POST | `migrateWeight` | write |  |
| `RenphoHealth/card/questionnaire/select` | POST | `questionnaireSelect` | read |  |
| `RenphoHealth/card/questionnaire/skip` | POST | `skipQuestionnaire` | write |  |
| `RenphoHealth/card/questionnaire/sub` | POST | `questionnaireSub` | write |  |
| `RenphoHealth/card/setCal` | POST | `setCal` | write |  |
| `RenphoHealth/card/updateCardRelationship` | POST | `updateCardRelationship` | write |  |

</details>

<details>
<summary><code>RenphoHealth/centerUser/</code> — 46 endpoints (5 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/centerUser/addFamilyMember` | POST | `addBabyMember`, `addMember` | write |  |
| `RenphoHealth/centerUser/addMigrateAcknowledge` | POST | `addMigrateAcknowledge` | write |  |
| `RenphoHealth/centerUser/authCodeCheck` | POST | `authCodeCheck` | account |  |
| `RenphoHealth/centerUser/batch/binding` | POST | `batchBinding` | write |  |
| `RenphoHealth/centerUser/cancelBindRopeDevice` | — | — | write |  |
| `RenphoHealth/centerUser/changeEmail` | POST | `changeEmail` | account |  |
| `RenphoHealth/centerUser/changePassword` | POST | `modifyPass` | account |  |
| `RenphoHealth/centerUser/changePasswordByOldPass` | POST | `updateUsePwd` | account |  |
| `RenphoHealth/centerUser/checkRingBind` | — | — | read |  |
| `RenphoHealth/centerUser/connectDevice` | POST | `bindDevice` | write |  |
| `RenphoHealth/centerUser/countFamilyMember` | POST | `queryMemberCount` | read | 🔎 verified |
| `RenphoHealth/centerUser/deleteFamilyMember` | — | — | write |  |
| `RenphoHealth/centerUser/deleteUser` | POST | `deleteAccount` | account |  |
| `RenphoHealth/centerUser/deviceInfo/v2` | — | — | ? | ❌ 1003 with {} |
| `RenphoHealth/centerUser/emailValid` | POST | `emailValid` | account |  |
| `RenphoHealth/centerUser/getBackUpEmail` | POST | `getBackUpEmail` | account |  |
| `RenphoHealth/centerUser/getEmailValidStatus` | POST | `getEmailValidStatus` | account |  |
| `RenphoHealth/centerUser/getMigrateGuide` | POST | `getMigrateGuide` | read |  |
| `RenphoHealth/centerUser/getTimeStamp` | POST | `getTimeStamp` | read | 🔎 verified |
| `RenphoHealth/centerUser/getUserUuid` | POST | `getUserUuid` | read |  |
| `RenphoHealth/centerUser/isFirstLogin` | POST | `getIsFirstLogin` | account |  |
| `RenphoHealth/centerUser/loginByWordCommand` | POST | `loginByWordCommand` | account |  |
| `RenphoHealth/centerUser/loginTuyaUser` | — | — | account |  |
| `RenphoHealth/centerUser/loginUser` | POST | `login` | account |  |
| `RenphoHealth/centerUser/logoutUser` | POST | `quitApp` | account |  |
| `RenphoHealth/centerUser/queryFamilyMemberList` | POST | `queryMemberList` | read | ✅ used |
| `RenphoHealth/centerUser/queryFamilyMemberListV2` | POST | `queryMemberListV2` | read | 🔎 verified |
| `RenphoHealth/centerUser/queryOneFamilyMember/` | — | — | read |  |
| `RenphoHealth/centerUser/registerUser/v2` | POST | `registerUser` | account |  |
| `RenphoHealth/centerUser/registerUserCount` | POST | `getAppRegisterUserCount` | account |  |
| `RenphoHealth/centerUser/setBackUpEmail` | POST | `setBackUpEmail` | account |  |
| `RenphoHealth/centerUser/setMethod` | POST | `setMethod` | account |  |
| `RenphoHealth/centerUser/setPassword` | POST | `setPassword` | account |  |
| `RenphoHealth/centerUser/setRevise` | POST | `setRevise` | account |  |
| `RenphoHealth/centerUser/subscription` | POST | `getUserSubscription` | write |  |
| `RenphoHealth/centerUser/thirdLoginCheck` | POST | `thirdLoginCheck` | account |  |
| `RenphoHealth/centerUser/toMain` | POST | `toMain` | write |  |
| `RenphoHealth/centerUser/updateDeviceNickName` | POST | `changeDeviceName` | write |  |
| `RenphoHealth/centerUser/updateFamilyMemberInfo` | POST | `updateFamilyMemberInfoNew`, `updateMemberInfo` | write |  |
| `RenphoHealth/centerUser/updateUser` | POST | `setUserInfo` | write |  |
| `RenphoHealth/centerUser/uploadGuidePageRecord` | POST | `uploadGuidePageRecord` | write |  |
| `RenphoHealth/centerUser/verifyEmailCode` | POST | `checkCode` | account |  |
| `RenphoHealth/centerUser/verifyEmailEnabled` | POST | `sendCode` | account |  |
| `RenphoHealth/centerUser/verifyEmailStatus` | POST | `checkEmailFull` | account |  |
| `RenphoHealth/centerUser/verifyPassword` | POST | `verifyPassword` | account |  |
| `RenphoHealth/centerUser/verifyPassword/v2` | POST | `verifyPasswordV2` | account |  |

</details>

<details>
<summary><code>RenphoHealth/coding/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/coding/list` | POST | `codingList` | read |  |

</details>

<details>
<summary><code>RenphoHealth/contentContainer/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/contentContainer/get` | POST | `getBannerContainerSource` | read |  |

</details>

<details>
<summary><code>RenphoHealth/device/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/device/history/deviceProbing` | POST | `getDeviceProbingNew` | read |  |
| `RenphoHealth/device/history/firstBind` | POST | `firstBind` | ? |  |
| `RenphoHealth/device/history/reportFirstBind` | POST | `reportFirstBind` | write |  |

</details>

<details>
<summary><code>RenphoHealth/feedback/</code> — 10 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/feedback/device/app/deviceLabels` | POST | `getFeedbackLabels` | read |  |
| `RenphoHealth/feedback/device/app/feedbackId` | POST | `getFeedBackId` | read |  |
| `RenphoHealth/feedback/device/app/list` | POST | `getFeedbackDeviceList` | read |  |
| `RenphoHealth/feedback/device/app/selectDeviceListAndLabels` | — | — | read |  |
| `RenphoHealth/feedback/order/app/add` | POST | `addFeedback` | write |  |
| `RenphoHealth/feedback/order/app/detail` | POST | `getTapeOrderList` | read |  |
| `RenphoHealth/feedback/order/app/list` | — | — | read |  |
| `RenphoHealth/feedback/order/app/reply` | POST | `feedbackReply` | ? |  |
| `RenphoHealth/feedback/order/app/setIsRead` | POST | `setOrderReading` | write |  |
| `RenphoHealth/feedback/order/app/whetherRead` | POST | `checkHasNewMsg` | read |  |

</details>

<details>
<summary><code>RenphoHealth/firebase/</code> — 4 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/firebase/notice/click` | — | — | write |  |
| `RenphoHealth/firebase/notice/getPermit` | — | — | read |  |
| `RenphoHealth/firebase/notice/refreshPermit` | — | — | write |  |
| `RenphoHealth/firebase/notice/refreshToken` | POST | `refreshToken` | write |  |

</details>

<details>
<summary><code>RenphoHealth/healthManage/</code> — 12 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/healthManage/confirmUpgradePanel` | POST | `scaleMigration` | write |  |
| `RenphoHealth/healthManage/createCustomActivityTemplate` | POST | `createCustomAct` | write |  |
| `RenphoHealth/healthManage/deleteActivity` | POST | `deleteActivity` | write |  |
| `RenphoHealth/healthManage/deleteRecentOrCustomActivityTemplate` | POST | `deleteActType` | write |  |
| `RenphoHealth/healthManage/getActivity` | POST | `getActManagementList` | read |  |
| `RenphoHealth/healthManage/getIcon` | POST | `getIcon` | read |  |
| `RenphoHealth/healthManage/getRecentData` | — | — | read |  |
| `RenphoHealth/healthManage/recordActivity` | POST | `recordAct` | write |  |
| `RenphoHealth/healthManage/selectActivityTemplate` | POST | `queryActTypeList` | read |  |
| `RenphoHealth/healthManage/setGoal` | POST | `setGoal` | write |  |
| `RenphoHealth/healthManage/staticGoal` | POST | `queryStaticGoalRecords` | read |  |
| `RenphoHealth/healthManage/updateGoal` | POST | `uploadGoal` | write |  |

</details>

<details>
<summary><code>RenphoHealth/logan/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/logan/logSwitch` | POST | `logSwitch` | ? |  |

</details>

<details>
<summary><code>RenphoHealth/method/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/method/decide` | POST | `methodDecide` | ? |  |

</details>

<details>
<summary><code>RenphoHealth/nutrition/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/nutrition/scale/deleteSlot` | POST | `deleteSlot` | write |  |
| `RenphoHealth/nutrition/scale/getDeviceSlotDetail` | POST | `getDeviceSlotDetail` | read |  |
| `RenphoHealth/nutrition/scale/registerSlot` | POST | `registerSlot` | account |  |

</details>

<details>
<summary><code>RenphoHealth/operation/</code> — 6 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/operation/card/getCardCuesMessage` | — | — | read |  |
| `RenphoHealth/operation/deleteUserCard` | — | — | account |  |
| `RenphoHealth/operation/deviceConfig/list` | POST | `requestDeviceConfig` | read |  |
| `RenphoHealth/operation/getDeviceConfig` | — | — | read |  |
| `RenphoHealth/operation/getFailDesc` | POST | `getConnectFailedDes` | read |  |
| `RenphoHealth/operation/insertUserCard` | — | — | write |  |

</details>

<details>
<summary><code>RenphoHealth/panel/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/panel/batchPullPanel` | POST | `getRnVersionInfo` | write |  |
| `RenphoHealth/panel/getPanelByName` | POST | `getPanelInfo` | read |  |
| `RenphoHealth/panel/guestBatchPullPanel` | POST | `getRnVersionInfoInTouristMode` | read |  |

</details>

<details>
<summary><code>RenphoHealth/ranking/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/ranking/rope/weeklyGoalList` | POST | `getWeeklyGoalList` | read |  |
| `RenphoHealth/ranking/rope/whetherRopeGoals` | POST | `checkIsSetSportGoal` | read |  |

</details>

<details>
<summary><code>RenphoHealth/renpho/</code> — 19 endpoints (3 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/renpho/girth/addUserFamily` | POST | `uploadNewUser` | write |  |
| `RenphoHealth/renpho/girth/deleteGirthsAllData` | POST | `deleteTapeData` | write |  |
| `RenphoHealth/renpho/girth/deleteGirthsAllDataV2` | POST | `deleteTapeDataForever` | write |  |
| `RenphoHealth/renpho/girth/deleteGirthsData` | POST | `deleteCustomBody` | write |  |
| `RenphoHealth/renpho/girth/deleteUserFamily` | POST | `tapeDeleteUser` | account |  |
| `RenphoHealth/renpho/girth/getUserGirthsType` | POST | `getCustomBody` | read |  |
| `RenphoHealth/renpho/girth/getUserGirthsTypeV1` | POST | `getTapeCustomBodyV1` | read |  |
| `RenphoHealth/renpho/girth/girthsCollect` | POST | `uploadTapeCollect` | write |  |
| `RenphoHealth/renpho/girth/insertGirthsData` | POST | `addCustomBody` | write |  |
| `RenphoHealth/renpho/girth/queryAllGirthsDataCount` | POST | `getAllUserTapeCount` | read |  |
| `RenphoHealth/renpho/girth/queryAllGirthsDataList` | POST | `getAllUserTapeData` | read | ✅ used |
| `RenphoHealth/renpho/girth/queryGirthsGoals` | POST | `getTapeGoals` | read | 🧪 experimental |
| `RenphoHealth/renpho/girth/selectGirthsCollectByUserId` | POST | `getTapeCollect` | read |  |
| `RenphoHealth/renpho/girth/selectUserByUnit` | POST | `getTapeUnit` | read |  |
| `RenphoHealth/renpho/girth/setFinishGirthsGoals` | POST | `setFinishGirthsGoals` | write |  |
| `RenphoHealth/renpho/girth/setGirthsGoalsV2` | POST | `setTapeGoalsV2` | write |  |
| `RenphoHealth/renpho/girth/updateGirthsCustomByUserIdJoinSlot` | POST | `modifyCustomBodyName` | write |  |
| `RenphoHealth/renpho/girth/updateUserByUnit` | POST | `setTapeUnit` | write |  |
| `RenphoHealth/renpho/girth/uploadGirthsDataV2` | POST | `uploadTapeDataV2` | write | ✅ used |

</details>

<details>
<summary><code>RenphoHealth/rope/</code> — 4 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/rope/counts` | POST | `getRopeDataSize` | read |  |
| `RenphoHealth/rope/deleteRopeDataBatch` | POST | `deleteRopeDataBatch` | write |  |
| `RenphoHealth/rope/selectMany` | POST | `getRopeData` | read |  |
| `RenphoHealth/rope/uploadOneRopeData` | POST | `uploadRopeData` | write |  |

</details>

<details>
<summary><code>RenphoHealth/scale/</code> — 30 endpoints (11 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/scale/action` | POST | `syncRenphoData` | ? |  |
| `RenphoHealth/scale/batchSetGoalInitial` | POST | `replenishBodyGoal` | write |  |
| `RenphoHealth/scale/bodyCompositionScaleCount` | POST | `getCompositionDataCount` | read | 🔎 verified |
| `RenphoHealth/scale/countAll` | — | — | read | ✅ used |
| `RenphoHealth/scale/countGoalRecord` | POST | `countGoalRecord` | read | 🔎 verified |
| `RenphoHealth/scale/createGoalRecord` | POST | `createGoalRecord` | write |  |
| `RenphoHealth/scale/createMeasureData` | POST | `uploadBabyMeasureData` | write |  |
| `RenphoHealth/scale/createMeasureRemark/` | POST | `createMeasureDataRemark` | write |  |
| `RenphoHealth/scale/deleteMeasureData/` | — | — | write |  |
| `RenphoHealth/scale/getAllOfflineMeasureDataRes` | POST | `getAllOfflineMeasureDataRes` | read |  |
| `RenphoHealth/scale/getOfflineMeasureDataRes` | POST | `getOfflineMeasureDataRes` | read |  |
| `RenphoHealth/scale/getThirdPartyDatasource` | POST | `getThirdPartyDatasource` | read | 🧪 experimental |
| `RenphoHealth/scale/getUserIdMappingTableNames` | POST | `getAllBodyScaleTable` | read | 🔎 verified |
| `RenphoHealth/scale/goalRecordUpload` | POST | `goalRecordUpload` | write |  |
| `RenphoHealth/scale/prepare` | POST | `syncRenphoDataPrepare` | ? |  |
| `RenphoHealth/scale/queryAllMeasureDataList/` | POST | `getBodyScaleDataByPage` | read | ✅ used |
| `RenphoHealth/scale/queryBodyCompositionMeasureData` | POST | `getCompositionMeasureData` | read | ✅ used |
| `RenphoHealth/scale/queryGoalRecord` | POST | `queryAllGoalRecord` | read | ❌ 1003 with {} |
| `RenphoHealth/scale/queryGoalRecords` | POST | `getCompositionGoalData`, `queryGoalRecords` | read | 🔎 verified |
| `RenphoHealth/scale/queryGoalRecordsV2` | POST | `queryGoalRecordsV2` | read | 🧪 experimental |
| `RenphoHealth/scale/queryMeasureData` | — | — | read |  |
| `RenphoHealth/scale/queryThirdPartyMeasureData` | POST | `queryThirdPartyMeasureData` | read | 🧪 experimental |
| `RenphoHealth/scale/saveUserGoal` | POST | `saveUserGoal` | write |  |
| `RenphoHealth/scale/syncStatus` | POST | `syncPartToThirdStatus` | ? |  |
| `RenphoHealth/scale/updateGoalRecord` | — | — | write |  |
| `RenphoHealth/scale/updateThirdPartyDatasource` | POST | `updateThirdPartyDatasource` | write |  |
| `RenphoHealth/scale/uploadMeasureData` | POST | `uploadCompScaleMeasureData`, `uploadMeasureData` | write |  |
| `RenphoHealth/scale/uploadOfflineMeasureData` | POST | `uploadOfflineMeasureData` | write |  |
| `RenphoHealth/scale/userGoal` | POST | `deleteGoal` | write |  |
| `RenphoHealth/scale/v1.0/deleteMeasureData` | POST | `deleteBodyScalesBabyData` | write |  |

</details>

<details>
<summary><code>RenphoHealth/setting/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/setting/get` | POST | `userSettingPull` | read |  |
| `RenphoHealth/setting/set` | POST | `userSettingUpload` | write |  |

</details>

<details>
<summary><code>RenphoHealth/sys_lang/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/sys_lang/check` | POST | `appTranslateTextCheck` | read |  |

</details>

<details>
<summary><code>RenphoHealth/va/</code> — 13 endpoints (1 documented below)</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `RenphoHealth/va/scale/batchModifyBaseWeight` | POST | `batchUpdateUserWeight` | write |  |
| `RenphoHealth/va/scale/delVaScaleByDeviceNumberAndSlot` | — | — | write |  |
| `RenphoHealth/va/scale/delVaScaleByUserId` | — | — | write |  |
| `RenphoHealth/va/scale/detectPairWifi` | POST | `scaleIsNet` | ? |  |
| `RenphoHealth/va/scale/findVaScaleByDeviceNumberOrUserId` | POST | `getDualModeUser` | read |  |
| `RenphoHealth/va/scale/getAllDualModeMeasurementByMac` | POST | `getAllDividerData` | read |  |
| `RenphoHealth/va/scale/getAllDualModeMeasurementCountByUserId` | POST | `getAllOfflineDivideNumber` | read |  |
| `RenphoHealth/va/scale/getDualModeMeasurementByMac` | POST | `getOfflineDataByUser` | read | 🧪 experimental |
| `RenphoHealth/va/scale/getDualModeMeasurementCountByUserId` | POST | `getOfflineDivideNumber` | read |  |
| `RenphoHealth/va/scale/insert` | — | — | write |  |
| `RenphoHealth/va/scale/insertOrModifyPairWifi` | — | — | write |  |
| `RenphoHealth/va/scale/modifyBaseWeight` | POST | `updateUserWeight` | write |  |
| `RenphoHealth/va/scale/unknownMeasurementsCallback` | POST | `downloadFile` | ? |  |

</details>

<details>
<summary><code>renpho-dual-mode-scale/renpho/</code> — 7 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-dual-mode-scale/renpho/wifiscale/getReportWifiPairLogByDeviceNumber` | POST | `getWifiPairInfo` | read |  |
| `renpho-dual-mode-scale/renpho/wifiscale/obtainGuestUpgradeDeviceList` | POST | `obtainGuestUpgradeDeviceList` | read |  |
| `renpho-dual-mode-scale/renpho/wifiscale/obtainUpgradeDeviceListByUserId` | POST | `obtainUpgradeDeviceListByUserId` | read |  |
| `renpho-dual-mode-scale/renpho/wifiscale/otaUpgradeCallback` | POST | `otaUpgradeCallback` | ? |  |
| `renpho-dual-mode-scale/renpho/wifiscale/pushAppUpGradeLastInfo` | POST | `pushAppUpGradeLastInfo` | write |  |
| `renpho-dual-mode-scale/renpho/wifiscale/reportWifiPairLog` | POST | `setWifiPairLog` | write |  |
| `renpho-dual-mode-scale/renpho/wifiscale/resetWifiPair` | POST | `resetTftWifiPair` | write |  |

</details>

<details>
<summary><code>renpho-treadmill/activity/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/activity/details` | — | — | read |  |
| `renpho-treadmill/activity/page` | — | — | ? |  |
| `renpho-treadmill/activity/participate` | — | — | ? |  |

</details>

<details>
<summary><code>renpho-treadmill/app/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/app/scenery/detail` | — | — | read |  |
| `renpho-treadmill/app/scenery/list` | — | — | read |  |

</details>

<details>
<summary><code>renpho-treadmill/challenge/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/challenge/best` | — | — | ? |  |
| `renpho-treadmill/challenge/history` | — | — | ? |  |

</details>

<details>
<summary><code>renpho-treadmill/home/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/home/insertCustomInfo` | — | — | write |  |
| `renpho-treadmill/home/retrieve` | — | — | ? |  |

</details>

<details>
<summary><code>renpho-treadmill/medal/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/medal/milestone` | — | — | ? |  |
| `renpho-treadmill/medal/milestone/detail` | — | — | read |  |

</details>

<details>
<summary><code>renpho-treadmill/mode/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/mode/map/delete` | — | — | write |  |
| `renpho-treadmill/mode/map/list` | — | — | read |  |

</details>

<details>
<summary><code>renpho-treadmill/model/</code> — 7 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/model/delete` | — | — | write |  |
| `renpho-treadmill/model/detail` | — | — | read |  |
| `renpho-treadmill/model/edit` | — | — | write |  |
| `renpho-treadmill/model/insert` | — | — | write |  |
| `renpho-treadmill/model/list` | — | — | read |  |
| `renpho-treadmill/model/presetModeDetail` | — | — | ? |  |
| `renpho-treadmill/model/presetModeList` | — | — | ? |  |

</details>

<details>
<summary><code>renpho-treadmill/rank/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/rank/enable` | — | — | ? |  |
| `renpho-treadmill/rank/getRank` | — | — | read |  |

</details>

<details>
<summary><code>renpho-treadmill/runningRecord/</code> — 7 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/runningRecord/delete` | — | — | write |  |
| `renpho-treadmill/runningRecord/record/details` | — | — | read |  |
| `renpho-treadmill/runningRecord/record/histogram` | — | — | ? |  |
| `renpho-treadmill/runningRecord/record/sportsStatistics` | — | — | ? |  |
| `renpho-treadmill/runningRecord/reportOfflineData` | — | — | write |  |
| `renpho-treadmill/runningRecord/upload` | — | — | write |  |
| `renpho-treadmill/runningRecord/uploadFatPercentageRecord` | — | — | write |  |

</details>

<details>
<summary><code>renpho-treadmill/unit/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/unit/insert` | — | — | write |  |

</details>

<details>
<summary><code>renpho-treadmill/weekGoals/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-treadmill/weekGoals/details` | — | — | read |  |
| `renpho-treadmill/weekGoals/list` | — | — | read |  |
| `renpho-treadmill/weekGoals/saveOrUpdate` | — | — | write |  |

</details>

<details>
<summary><code>renpho-ring/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/getFactor` | POST | `getRingFactor` | read |  |

</details>

<details>
<summary><code>renpho-ring/aggregation/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/aggregation/count` | POST | `gotRingDataCount` | read |  |

</details>

<details>
<summary><code>renpho-ring/bloodyOxygen/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/bloodyOxygen/get` | POST | `gotRingBloodOxygenData` | read |  |
| `renpho-ring/bloodyOxygen/upload` | POST | `uploadBloodOxygenData` | write |  |

</details>

<details>
<summary><code>renpho-ring/firebase/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/firebase/push` | POST | `ringPeriodFirebasePush` | write |  |

</details>

<details>
<summary><code>renpho-ring/goal/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/goal/get` | POST | `gotRingGoalData` | read |  |
| `renpho-ring/goal/upload` | POST | `uploadRingGoal` | write |  |

</details>

<details>
<summary><code>renpho-ring/heartRate/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/heartRate/get` | POST | `gotRingHeartRateData` | read |  |
| `renpho-ring/heartRate/upload` | POST | `uploadHeartRateData` | write |  |

</details>

<details>
<summary><code>renpho-ring/hrv/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/hrv/get` | POST | `gotRingHrvData` | read |  |
| `renpho-ring/hrv/upload` | POST | `uploadHrvData` | write |  |

</details>

<details>
<summary><code>renpho-ring/menstruation/</code> — 4 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/menstruation/get` | POST | `getMenstruationData` | read |  |
| `renpho-ring/menstruation/getSymptom` | POST | `getSymptomData` | read |  |
| `renpho-ring/menstruation/upload` | POST | `uploadMenstruationData` | write |  |
| `renpho-ring/menstruation/uploadSymptoms` | POST | `uploadSymptomsData` | write |  |

</details>

<details>
<summary><code>renpho-ring/sleep/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/sleep/get` | POST | `gotRingSleepData` | read |  |
| `renpho-ring/sleep/upload` | POST | `uploadSleepData` | write |  |
| `renpho-ring/sleep/uploadSleepScore` | POST | `uploadSleepScore` | write |  |

</details>

<details>
<summary><code>renpho-ring/sportData/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/sportData/deleteById` | POST | `deleteRingSportData` | write |  |
| `renpho-ring/sportData/get` | POST | `getRingSportData` | read |  |
| `renpho-ring/sportData/upload` | POST | `uploadRingSportData` | write |  |

</details>

<details>
<summary><code>renpho-ring/step/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-ring/step/get` | POST | `gotRingStepData` | read |  |
| `renpho-ring/step/setStepGoal` | POST | `setStepGoal` | write |  |
| `renpho-ring/step/upload` | POST | `upLoadStepData` | write |  |

</details>

<details>
<summary><code>renpho-sphygmomanometer/measuringRecord/</code> — 6 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-sphygmomanometer/measuringRecord/batch/add` | POST | `bloodBatchAdd` | write |  |
| `renpho-sphygmomanometer/measuringRecord/batch/pull` | POST | `bloodBatchPull` | ? |  |
| `renpho-sphygmomanometer/measuringRecord/checkRecordCount` | POST | `checkBloodPressureCount` | read |  |
| `renpho-sphygmomanometer/measuringRecord/deleteByIds` | POST | `bloodDeleteByIds` | write |  |
| `renpho-sphygmomanometer/measuringRecord/latest` | — | — | ? |  |
| `renpho-sphygmomanometer/measuringRecord/update` | POST | `bloodUpdateRecord` | write |  |

</details>

<details>
<summary><code>renpho-foodscale-gennec-sync//</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-foodscale-gennec-sync//health/food/meal/record/update` | POST | `editMealRecord` | write |  |

</details>

<details>
<summary><code>renpho-foodscale-gennec-sync/foodLib/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-foodscale-gennec-sync/foodLib/batchAdd` | POST | `batchAdd` | write |  |
| `renpho-foodscale-gennec-sync/foodLib/batchDelete` | POST | `batchDelete` | write |  |
| `renpho-foodscale-gennec-sync/foodLib/list` | POST | `getFoodLibList` | read |  |

</details>

<details>
<summary><code>renpho-foodscale-gennec-sync/health/</code> — 34 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-foodscale-gennec-sync/health/food/action/collect/add` | POST | `addCollectFood` | write |  |
| `renpho-foodscale-gennec-sync/health/food/action/collect/delete` | POST | `deleteCollectFood` | write |  |
| `renpho-foodscale-gennec-sync/health/food/action/collect/refreshPicture` | POST | `notifyRefreshFavorite` | write |  |
| `renpho-foodscale-gennec-sync/health/food/action/diy/add` | POST | `addCustomerFood` | write |  |
| `renpho-foodscale-gennec-sync/health/food/action/diy/delete` | POST | `deleteCustomFood` | write |  |
| `renpho-foodscale-gennec-sync/health/food/action/diy/update` | POST | `updateCustomerFood` | write |  |
| `renpho-foodscale-gennec-sync/health/food/action/query/byBarCode/v2` | POST | `queryFoodByBarCode` | read |  |
| `renpho-foodscale-gennec-sync/health/food/action/query/byName/v2` | POST | `queryFoodByName` | read |  |
| `renpho-foodscale-gennec-sync/health/food/action/recent/refreshPicture` | POST | `notifyRefreshRecent` | write |  |
| `renpho-foodscale-gennec-sync/health/food/drink/addOrUpdate` | POST | `addOrUpdateDrink` | write |  |
| `renpho-foodscale-gennec-sync/health/food/drink/query` | POST | `queryNatureScaleDrinkRecord` | read |  |
| `renpho-foodscale-gennec-sync/health/food/gennec/getUserInfo` | POST | `getTuyaUserInfo` | read |  |
| `renpho-foodscale-gennec-sync/health/food/gennec/sync` | POST | `syncGennecData` | ? |  |
| `renpho-foodscale-gennec-sync/health/food/goal/add` | POST | `insertNatureScaleGoal` | write |  |
| `renpho-foodscale-gennec-sync/health/food/goal/query` | POST | `queryNatureScaleGoal` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/addMeal` | POST | `addMeal` | write |  |
| `renpho-foodscale-gennec-sync/health/food/meal/addMeal/v2` | POST | `addMealV2` | write |  |
| `renpho-foodscale-gennec-sync/health/food/meal/collect/list` | POST | `queryMealCollectList` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/copy` | POST | `copyMeal` | ? |  |
| `renpho-foodscale-gennec-sync/health/food/meal/countAll` | POST | `getFoodMealCount` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/custom/list` | POST | `getCustomFoodList` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/dailyInfo` | POST | `getDailyMealInfo` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/deleteRecord` | POST | `deleteMealRecord` | write |  |
| `renpho-foodscale-gennec-sync/health/food/meal/detailInfo` | POST | `getMealDetailInfo` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/queryAll` | POST | `getFoodMeal` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/queryFoodDetail/v2` | POST | `queryFoodDetail` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/queryFoodPopular` | POST | `queryMealPopularList` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/queryFoodQuality` | POST | `queryFoodQuality` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/recent/list` | POST | `queryMealRecentList` | read |  |
| `renpho-foodscale-gennec-sync/health/food/meal/syncMealList` | POST | `devSyncMealList` | ? |  |
| `renpho-foodscale-gennec-sync/health/food/module/query` | POST | `queryWidgetGoalData` | read |  |
| `renpho-foodscale-gennec-sync/health/food/setting/dailyExercise` | POST | `queryDailyExercise` | read |  |
| `renpho-foodscale-gennec-sync/health/food/setting/query` | POST | `foodSettingQuery` | read |  |
| `renpho-foodscale-gennec-sync/health/food/setting/refresh` | POST | `refreshFoodSetting` | write |  |

</details>

<details>
<summary><code>renpho-foodscale-gennec-sync/renpho/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-foodscale-gennec-sync/renpho/health/food/common/selectPid` | — | — | read |  |

</details>

<details>
<summary><code>renpho-foodscale-gennec-sync/solution/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-foodscale-gennec-sync/solution/health/food/meal/getUserMeal` | — | — | read |  |

</details>

<details>
<summary><code>centerUser/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `centerUser/motionStaticsSum` | POST | `getRopeMotionStaticsSum` | read |  |

</details>

<details>
<summary><code>community-service/community/</code> — 14 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `community-service/community/message/getDeletePost` | POST | `getDeleteReportPost` | read |  |
| `community-service/community/message/list` | POST | `userNewsList` | read |  |
| `community-service/community/message/noConfirmCount` | POST | `isHaveNewMsg` | read |  |
| `community-service/community/message/userUnReadCheckMessage` | POST | `isHaveNoReadMsg` | read |  |
| `community-service/community/post/translate` | POST | `translateContent` | ? |  |
| `community-service/community/user/editBio` | POST | `editBio` | write |  |
| `community-service/community/user/follow/cancelFollow` | POST | `cancelFollow` | write |  |
| `community-service/community/user/follow/follow` | POST | `following` | ? |  |
| `community-service/community/user/follow/follower/list` | POST | `userFollower` | read |  |
| `community-service/community/user/follow/following/list` | POST | `userFollowing` | read |  |
| `community-service/community/user/follow/list` | POST | `getFollows` | read |  |
| `community-service/community/user/follow/totalNewFollow` | POST | `newFollowCount` | ? |  |
| `community-service/community/user/userInfo/get` | POST | `getPostUserInfo` | read |  |
| `community-service/community/user/userSetting/edit` | POST | `changePrivacy` | write |  |

</details>

<details>
<summary><code>community-service/post/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `community-service/post/comment/fromMessage` | POST | `getSingleComment` | read |  |
| `community-service/post/comment/list` | POST | `getComment`, `getSecondComment` | read |  |

</details>

<details>
<summary><code>community-service/user/</code> — 14 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `community-service/user/comment/delete` | POST | `deleteComment` | write |  |
| `community-service/user/post` | POST | `posting` | ? |  |
| `community-service/user/post/comment` | POST | `postComment`, `postSecondComment` | ? |  |
| `community-service/user/post/delete` | POST | `deletePost` | write |  |
| `community-service/user/post/detail` | POST | `getPostDetail` | read |  |
| `community-service/user/post/edit` | POST | `rePost` | write |  |
| `community-service/user/post/like` | POST | `likePost` | ? |  |
| `community-service/user/post/list` | POST | `getPostList` | read |  |
| `community-service/user/post/report` | POST | `reportPost` | write |  |
| `community-service/user/post/reportCategory` | POST | `getReportType` | write |  |
| `community-service/user/post/reportCheck` | POST | `isReported` | write |  |
| `community-service/user/post/reportInfo` | POST | `getReportPost` | write |  |
| `community-service/user/post/userLike` | POST | `userLikeList` | ? |  |
| `community-service/user/post/userList` | POST | `userPostList` | ? |  |

</details>

<details>
<summary><code>mall-service/mall/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `mall-service/mall/banner/enableBannerByUserId` | POST | `enableBannerByUserId` | ? |  |
| `mall-service/mall/banner/findBannerByUserId` | POST | `findBannerByUserId` | read |  |
| `mall-service/mall/order/count` | POST | `orderCount` | read |  |

</details>

<details>
<summary><code>openApi/facade/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `openApi/facade/show/v2` | POST | `getSplashConfig` | read |  |

</details>

<details>
<summary><code>openApi/v1.0/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `openApi/v1.0/multiUpload/{type}` | POST | `uploadMorePic` | write |  |
| `openApi/v1.0/upload/{name}` | POST | `feedbackUploadPic`, `uploadAvatar`, `uploadFeedBackPic`, `uploadPic`, `uploadSubAvatar`, `uploadUserAvatar` | account |  |

</details>

<details>
<summary><code>openApi/v1.1/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `openApi/v1.1/uploadImg/food` | POST | `queryPicUploadConfig` | read |  |

</details>

<details>
<summary><code>renpho-aigym/course/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-aigym/course/fascial/data-upload` | POST | `reportSport` | write |  |

</details>

<details>
<summary><code>renpho-health-badge/badge/</code> — 2 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-health-badge/badge/user/getUpdateBadge` | — | — | read |  |
| `renpho-health-badge/badge/user/getUserBadgeInfoById` | — | — | read |  |

</details>

<details>
<summary><code>renpho-health-badge/userBadge/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-health-badge/userBadge/upload` | — | — | write |  |

</details>

<details>
<summary><code>renpho-health-badge/userOpenApp/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-health-badge/userOpenApp/upload` | — | — | write |  |

</details>

<details>
<summary><code>renpho-push/data/</code> — 1 endpoint</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `renpho-push/data/gif/logs/a18` | POST | `chooseVersionLog` | ? |  |

</details>

<details>
<summary><code>scale/</code> — 3 endpoints</summary>

| Path | HTTP | App method | Kind | Status |
| --- | --- | --- | --- | --- |
| `scale/cancelSync` | POST | `cancelFitnessSync`, `cancelSync` | write |  |
| `scale/querySubscribe` | POST | `queryFitnessState`, `querySubscribe` | read |  |
| `scale/syncMyFitnessPal` | POST | `syncMyFitnessPal` | ? |  |

</details>
