=========================================================
  FORWARD BOT — README
  BUILD: 2026-10-05-AUDIT-26
  (source ZC Course List -> target channel, full caption + purple bar)
=========================================================

---------------------------------------------------------
 1) GITHUB PE KYA UPLOAD KARNA HAI
---------------------------------------------------------
  MUST:
    1) bot.py            203,118 bytes   <<< MAIN
    2) mise.toml                223 B    (build fix)
    3) requirements.txt          47 B    (python-telegram-bot 21.6)
    4) railway.toml             132 B    (start: python bot.py)

  OPTIONAL (bad me kabhi):
    5) filter_data.json         ~0.9 KB  (source+target ready;
       upload karo to settings reset ho jaati hain)
    6) AB_KYA_KARO_FINAL.txt / SAB_RECHECK_REPORT.txt (docs)

  GitHub pe ZIP upload NAHI karna — file upload (Add file →
  Upload files). Phone se paste BILKUL NAHI (indent toot jaata hai).

---------------------------------------------------------
 2) UPLOAD KE BAAD (5 step)
---------------------------------------------------------
  1) Railway deploy khatam hone do (1-2 min)
  2) /ping   → BUILD: 2026-10-05-AUDIT-26
  3) /check  → "delete messages: YES" aur sab ✅
  4) /preview → source post DM me forward karo:
        • koi "Forwarded from ZC Course List" tag NAHI
        • PURPLE BAR (collapse wali)
        • Owner line + Contact Us button
  5) /clean on → /forward 45 13365

---------------------------------------------------------
 3) BOT ME KYA-KYA HAI (feature list)
---------------------------------------------------------
  BULK
    /forward FROM TO [SKIP] [DELAY]  — FROM se exactly start,
        har id try (koi mid-drop nahi), ek kharab id poora run
        nahi rokti (crash-proof), flood guard, /stop se rukta hai,
        /status se resume tip
    /copy ID                          — ek post bhejo
    /status /stop /skip /delay /duplicates

  POST KA LOOK
    • "Forwarded from ..." tag NAHI (file_id se fresh send)
    • PURPLE BAR (quote/collapse) har post me jisme source me
      bar ya list hai — 4-step chain + delivery verify
    • Owner line: Owner 👤 : @RicxyBhai (editable /captionfooter)
    • URL buttons (Contact Us) — /button "Contact Us | URL"
    • Header / template optional

  FILTER
    /block word      — word hatao
    /replace old new — word badlo (case-insensitive)
    /listfilters /unblock /unreplace

  CHANNELS
    /addsource /addtarget (link ya channel se post forward karo)
    /settarget (sirf 1) /removetarget /cleartargets /targets

  MODE
    /auto on|off    — live channel post forward (default OFF)
    /clean on|off   — NO-TAG CLEAN (default ON): pehle 1 SILENT
                      copy sirf file_id lene ke liye, phir wahi post
                      bina tag ke dobara bheji jaati hai, aur tag wali
                      copy turant DELETE (isi liye channel me 1 hi
                      post rehti hai). Delete permission na ho to bot
                      clean mode skip kar deta hai (2 post nahi banti).
    /quote on|off   — purple bar auto (default ON)
    /test /preview /captiondump /inspect ID /check /panic

  SAFETY
    • Post deliver ho chuki ho to retry NAHI (duplicate post nahi)
    • Protected content -> forward se jaata hai (post pahunchti hai)
    • sticker / video_note / poll / location sab safe
    • Koi temp-copy / hop / DM-copy system NAHI

---------------------------------------------------------
 4) RAILWAY VARIABLES (minimum)
---------------------------------------------------------
  BOT_TOKEN        = BotFather ka token
  ADMIN_IDS        = 8467972004,6312515331
  SOURCE_CHAT_ID   = -1003415196836
  (TARGET bot ke andar se set hota hai: /settarget /addtarget)

---------------------------------------------------------
 5) AGAR KUCH GALAT LAGE
---------------------------------------------------------
  /ping    -> bot zinda? kaunsa build?
  /check   -> source/target/permission/error
  /panic   -> ek command me auto-fix + verdict
  /status  -> forward ka progress
  Logs     -> Railway → Deploy Logs (build OK par reply nahi = runtime crash)
=========================================================
