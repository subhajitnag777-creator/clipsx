# Hosting Clips X on Cloudflare with R2 Storage

This guide explains how to host Clips X using **Cloudflare Tunnel** and store/stream all video clips using **Cloudflare R2 Object Storage** (with zero egress bandwidth fees).

---

## 1. Cloudflare R2 Storage Setup (Zero Egress Fees)

Cloudflare R2 replaces your local hard drive for video storage. When enabled, all clips and covers are uploaded directly to Cloudflare's edge network and streamed to users without consuming your host's bandwidth.

### Step 1: Create an R2 Bucket
1. Sign in to your [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. In the left navigation, click **R2 Object Storage**.
3. Click **Create bucket**.
4. Set **Bucket name** to `clipsx-media` (or your choice).
5. Choose **Default** (Automatic) location and click **Create Bucket**.

### Step 2: Generate R2 API Token
1. On the R2 dashboard, click **Manage R2 API Tokens** (top right).
2. Click **Create API token**.
3. Configure the token:
   - **Permissions**: Select **Object Read & Write**.
   - **Specify bucket(s)**: Select `clipsx-media` (or Apply to all buckets).
   - **TTL**: Forever (or your desired expiry).
4. Click **Create API Token**.
5. Copy the following credentials immediately (they are only shown once):
   - **Access Key ID** &rarr; `R2_ACCESS_KEY_ID`
   - **Secret Access Key** &rarr; `R2_SECRET_ACCESS_KEY`
   - **Account ID** (found in the endpoint URL or right sidebar) &rarr; `R2_ACCOUNT_ID`

### Step 3: (Optional but Recommended) Enable Public Access or Custom Domain
To stream videos directly from Cloudflare's global CDN:
1. Open your `clipsx-media` bucket in the Cloudflare dashboard.
2. Go to the **Settings** tab.
3. Under **Public Access**:
   - **Option A (Custom Domain)**: Click **Connect Domain** and enter a subdomain like `media.yourdomain.com` (Cloudflare sets up the DNS automatically).
   - **Option B (R2.dev Subdomain)**: Click **Allow Access** to get a free `pub-xxx.r2.dev` URL.
4. Copy this address into `R2_PUBLIC_URL`.

### Step 4: Update Your `.env`
Add these lines to your `.env`:

```dotenv
# ==========================================
# CLOUDFLARE R2 OBJECT STORAGE (ZERO-EGRESS)
# ==========================================
R2_ENABLED=true
R2_ACCOUNT_ID=your_32_character_account_id
R2_ACCESS_KEY_ID=your_r2_access_key_id
R2_SECRET_ACCESS_KEY=your_r2_secret_access_key
R2_BUCKET_NAME=clipsx-media
R2_PUBLIC_URL=https://media.yourdomain.com
R2_REGION=auto
```

### Step 5: Verify R2 in Clips X
1. Open Clips X &rarr; **Settings** &rarr; **Storage**.
2. Under **Cloudflare R2 Storage**, you will see **Active**.
3. Click **Test R2** to verify upload/read permissions.

---

## 2. Hosting with Cloudflare Tunnel (`cloudflared`)

Clips X requires Python and FFmpeg for video processing. Cloudflare Tunnel securely exposes your local machine or VPS to the internet through Cloudflare's edge with:
- Automatic free HTTPS (SSL/TLS).
- Zero open firewall ports (NAT traversal).
- Cloudflare DDoS protection and Turnstile bot filtering.

### Method A: One-Click Quick Tunnel (Free, No Setup Needed)
1. Start Clips X locally using `run.bat`.
2. Double-click `tunnel.bat` in the project root.
3. `tunnel.bat` will automatically download `cloudflared.exe` (if needed) and generate a secure public URL:
   ```
   https://random-subdomain.trycloudflare.com
   ```
4. Anyone can visit that link over HTTPS to use Clips X!

---

### Method B: Named Tunnel on Your Custom Domain (e.g. `clips.yourdomain.com`)
To host permanently on your own domain:

1. Open [Cloudflare Zero Trust](https://one.dash.cloudflare.com/).
2. Navigate to **Networks** &rarr; **Tunnels**.
3. Click **Create a tunnel**, choose **Cloudflare (cloudflared)**, and name it `clipsx`.
4. Cloudflare will display your **Tunnel Token** (a long string starting with `eyJh...`).
5. Copy the token into your `.env`:
   ```dotenv
   CLOUDFLARE_TUNNEL_TOKEN=eyJh...your_token_here...
   ```
6. On the **Public Hostname** tab in Cloudflare:
   - **Subdomain**: `clips`
   - **Domain**: `yourdomain.com`
   - **Type**: `HTTP`
   - **URL**: `localhost:8765` (or `app:8765` in Docker)
7. Save the hostname.
8. Double-click `tunnel.bat` or run:
   ```cmd
   cloudflared.exe tunnel run --token YOUR_TOKEN
   ```
9. Your site is now live at `https://clips.yourdomain.com`!

---

### Method C: Hosting on a Cloud VPS with Docker

If you want to run Clips X 24/7 on a cloud VPS (e.g. Hetzner, DigitalOcean, Oracle Cloud, AWS):

1. Clone your project onto the VPS:
   ```bash
   git clone <repo-url> /opt/clipsx
   cd /opt/clipsx
   ```
2. Copy and configure your `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Ensure `CLOUDFLARE_TUNNEL_TOKEN`, `R2_ENABLED`, and your OAuth/AI keys are set.
3. Launch with Docker Compose:
   ```bash
   docker compose up -d
   ```
4. Both Clips X and Cloudflare Tunnel will start and automatically reconnect on reboot.

---

## 3. Summary of Configuration Values

| Variable | Purpose |
|---|---|
| `R2_ENABLED` | Set `true` to enable Cloudflare R2 cloud storage |
| `R2_ACCOUNT_ID` | Your Cloudflare Account ID (found in Dashboard) |
| `R2_ACCESS_KEY_ID` | R2 API Token Access Key |
| `R2_SECRET_ACCESS_KEY` | R2 API Token Secret Key |
| `R2_BUCKET_NAME` | R2 Bucket name (e.g. `clipsx-media`) |
| `R2_PUBLIC_URL` | Public custom domain for bucket (e.g. `https://media.yourdomain.com`) |
| `CLOUDFLARE_TUNNEL_TOKEN` | Token for Cloudflare Named Tunnel |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile site key for bot protection |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key |
