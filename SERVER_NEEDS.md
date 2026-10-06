# ZC Forward Bot — server needs

- **Recommended start:** Ubuntu 22.04/24.04 VPS, 1 vCPU, 1 GB RAM, 5–10 GB SSD, stable always-on network.
- **Comfortable capacity:** 1–2 vCPU and 2 GB RAM for several active users/jobs.
- **MongoDB:** MongoDB Atlas free M0 is suitable to start. Allow the VPS IP in Atlas Network Access.
- **Deployment:** Docker Compose is included; it restarts automatically with `restart: unless-stopped`.
- **No media download for normal forwarding:** `copy_message` works in Telegram's cloud, so disk and CPU needs are low.
- **If FFmpeg media watermarking is added later:** upgrade to 2 vCPU, 2–4 GB RAM and more disk.

Never host multiple copies of this same bot against the same MongoDB jobs collection unless you add a distributed worker lock.
