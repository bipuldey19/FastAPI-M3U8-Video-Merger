# M3U8 Video Merger API - Production Deployment

A production-ready FastAPI service for merging multiple M3U8 video streams with beautiful overlays and transitions, optimized for Instagram Reels format (9:16).

## 🚀 Features

- **Reels Format**: Automatic conversion to 1080x1920 (9:16 aspect ratio)
- **Beautiful Overlays**: Animated text overlays with video numbers and titles
- **Smooth Transitions**: Professional transitions between videos
- **Production Ready**: Redis-backed job queue, rate limiting, health checks
- **Docker Support**: Complete containerization with Docker Compose
- **Nginx Proxy Manager Compatible**: Works seamlessly with NPM
- **Monitoring**: Health checks, logging, and status endpoints
- **Auto Cleanup**: Automatic cleanup of old files

## 📋 Prerequisites

- Docker & Docker Compose
- VPS with at least 4GB RAM
- FFmpeg (included in Docker image)
- Nginx Proxy Manager (optional, for domain/SSL management)

## 🛠️ Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd video-merger-api
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env  # Edit with your settings
```

### 3. Make deployment script executable

```bash
chmod +x deploy.sh
```

### 4. Start the services

```bash
./deploy.sh start
```

## 📁 Project Structure

```
video-merger-api/
├── main.py                 # Main FastAPI application
├── config.py              # Configuration settings
├── video_processor.py     # Video processing logic
├── rate_limiter.py        # Rate limiting middleware
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose setup
├── deploy.sh             # Deployment script
├── .env.example          # Environment template
├── output/               # Processed videos
├── logs/                 # Application logs
└── temp/                 # Temporary files
```

## 🔧 Configuration

### Environment Variables (.env)

```bash
# Application
DEBUG=false
HOST=0.0.0.0
PORT=8000
WORKERS=4
LOG_LEVEL=INFO

# API
RATE_LIMIT_PER_MINUTE=10
MAX_VIDEOS_PER_REQUEST=20

# Redis
REDIS_URL=redis://redis:6379/0

# Video Processing
REELS_WIDTH=1080
REELS_HEIGHT=1920
FFMPEG_PRESET=medium
FFMPEG_CRF=23

# Security (Configure for production!)
ALLOWED_ORIGINS=["https://yourdomain.com"]
TRUSTED_HOSTS=["yourdomain.com"]
```

## 🚦 Usage

### Start Services

```bash
./deploy.sh start
```

### Check Status

```bash
./deploy.sh status
```

### View Logs

```bash
./deploy.sh logs
```

### Stop Services

```bash
./deploy.sh stop
```

### Restart Services

```bash
./deploy.sh restart
```

### Cleanup Old Files

```bash
./deploy.sh cleanup
```

### Backup Data

```bash
./deploy.sh backup
```

## 📡 API Endpoints

### 1. Create Merge Job

**POST** `/api/merge`

```bash
curl -X POST "http://your-domain.com/api/merge" \
  -H "Content-Type: application/json" \
  -d '{
    "videos": [
      {
        "title": "Amazing Video 1",
        "secure_media": {
          "reddit_video": {
            "hls_url": "https://v.redd.it/example1/HLSPlaylist.m3u8"
          }
        },
        "url": "https://v.redd.it/example1"
      },
      {
        "title": "Cool Video 2",
        "secure_media": {
          "reddit_video": {
            "hls_url": "https://v.redd.it/example2/HLSPlaylist.m3u8"
          }
        },
        "url": "https://v.redd.it/example2"
      }
    ],
    "transition_duration": 0.5,
    "overlay_duration": 2.0
  }'
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "progress": "Job queued for processing"
}
```

### 2. Check Job Status

**GET** `/api/status/{job_id}`

```bash
curl "http://your-domain.com/api/status/550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": "Completed successfully!",
  "output_file": "output/550e8400-e29b-41d4-a716-446655440000.mp4",
  "created_at": "2025-10-08T10:30:00",
  "completed_at": "2025-10-08T10:35:00"
}
```

**Status Values:**
- `queued` - Job is waiting to be processed
- `downloading` - Downloading M3U8 streams
- `processing` - Processing videos with overlays
- `merging` - Merging videos with transitions
- `completed` - Job completed successfully
- `failed` - Job failed (check error field)

### 3. Download Video

**GET** `/api/download/{job_id}`

```bash
curl -O "http://your-domain.com/api/download/550e8400-e29b-41d4-a716-446655440000"
```

### 4. Delete Job

**DELETE** `/api/job/{job_id}`

```bash
curl -X DELETE "http://your-domain.com/api/job/550e8400-e29b-41d4-a716-446655440000"
```

### 5. Health Check

**GET** `/health`

```bash
curl "http://your-domain.com/health"
```

## 🔒 Security Recommendations

### 1. Configure CORS

Edit `.env`:
```bash
ALLOWED_ORIGINS=["https://yourdomain.com", "https://www.yourdomain.com"]
```

### 2. Setup with Nginx Proxy Manager

1. In NPM, add a new Proxy Host:
   - **Domain Names**: `api.yourdomain.com`
   - **Scheme**: `http`
   - **Forward Hostname/IP**: `your-vps-ip` or `localhost`
   - **Forward Port**: `8000`
   - **Cache Assets**: ✓ (optional)
   - **Block Common Exploits**: ✓
   - **Websockets Support**: ✓

2. SSL Tab:
   - **SSL Certificate**: Request a new SSL certificate
   - **Force SSL**: ✓
   - **HTTP/2 Support**: ✓
   - **HSTS Enabled**: ✓

3. Advanced Tab (optional):
   ```nginx
   # Rate limiting
   limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/m;
   limit_req zone=api_limit burst=5 nodelay;
   
   # Increase timeouts for video processing
   proxy_connect_timeout 60s;
   proxy_send_timeout 600s;
   proxy_read_timeout 600s;
   ```

### 3. Firewall Configuration

```bash
# Allow only essential ports
ufw allow 22/tcp    # SSH
ufw allow 8000/tcp  # API (if accessing directly)
ufw enable
```

### 4. Disable API Documentation in Production

```bash
ENABLE_DOCS=false
```

### 5. Set Strong Redis Password

Edit `docker-compose.yml`:
```yaml
redis:
  command: redis-server --requirepass your_strong_password
```

Update `.env`:
```bash
REDIS_URL=redis://:your_strong_password@redis:6379/0
```

## 📊 Monitoring

### Check Service Health

```bash
curl http://localhost:8000/health
```

### View Docker Stats

```bash
docker stats
```

### Check Disk Usage

```bash
./deploy.sh status
```

### View Application Logs

```bash
tail -f logs/app.log
```

## 🔄 Maintenance

### Update Application

```bash
./deploy.sh update
```

### Clean Up Old Files

```bash
./deploy.sh cleanup
```

### Backup Important Data

```bash
./deploy.sh backup
```

### Restart Services

```bash
./deploy.sh restart
```

## ⚡ Performance Optimization

### 1. Adjust FFmpeg Preset

Faster encoding (lower quality):
```bash
FFMPEG_PRESET=faster
```

Better quality (slower):
```bash
FFMPEG_PRESET=slow
```

### 2. Adjust Worker Count

Based on CPU cores:
```bash
WORKERS=8  # For 8-core CPU
```

### 3. Redis Memory Limit

Adjust in `docker-compose.yml`:
```yaml
command: redis-server --maxmemory 1gb
```

### 4. Increase Rate Limits

For higher traffic:
```bash
RATE_LIMIT_PER_MINUTE=100
```

## 🐛 Troubleshooting

### Services won't start

```bash
# Check logs
./deploy.sh logs

# Check Docker status
docker-compose ps
```

### Redis connection issues

```bash
# Test Redis connection
docker-compose exec redis redis-cli ping
```

### FFmpeg errors

```bash
# Check FFmpeg installation
docker-compose exec api ffmpeg -version
```

### Out of disk space

```bash
# Clean up old files
./deploy.sh cleanup

# Check disk usage
df -h
```

### Memory issues

```bash
# Check memory usage
free -h

# Reduce workers in .env
WORKERS=2
```

## 📝 License

MIT License - feel free to use in your projects!

## 🤝 Support

For issues and questions, please create an issue on GitHub.

## 🎯 Production Checklist

- [ ] Configure `.env` with production values
- [ ] Set strong Redis password
- [ ] Setup domain in Nginx Proxy Manager
- [ ] Enable SSL in Nginx Proxy Manager
- [ ] Configure CORS for your domain
- [ ] Disable API documentation (`ENABLE_DOCS=false`)
- [ ] Set up firewall rules
- [ ] Configure backup strategy
- [ ] Set up monitoring/alerting
- [ ] Test health check endpoints
- [ ] Configure log rotation
- [ ] Set appropriate rate limits
- [ ] Test failover scenarios

## 🚀 Deployment to VPS

### Quick Start

```bash
# 1. SSH into your VPS
ssh user@your-vps-ip

# 2. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 3. Install Docker Compose
sudo apt-get install docker-compose-plugin

# 4. Clone and configure
git clone <your-repo>
cd video-merger-api
cp .env.example .env
nano .env  # Configure

# 5. Deploy
chmod +x deploy.sh
./deploy.sh start
```

### Setup with Nginx Proxy Manager

After deployment, configure in NPM:

1. **Add Proxy Host**:
   - Domain: `api.yourdomain.com`
   - Forward to: `your-vps-ip:8000`
   - Enable SSL

2. **Test the API**:
```bash
curl https://api.yourdomain.com/health
```

Your API will be available at `https://api.yourdomain.com`!
