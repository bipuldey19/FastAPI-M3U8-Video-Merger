#!/bin/bash

# Video Merger API Deployment Script
# Usage: ./deploy.sh [start|stop|restart|logs|status]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

# Create necessary directories
setup_directories() {
    print_info "Creating necessary directories..."
    mkdir -p output logs temp ssl
    chmod 755 output logs temp
}

# Check if .env file exists
check_env() {
    if [ ! -f .env ]; then
        print_warning ".env file not found. Creating from .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            print_info "Please edit .env file with your configuration"
            exit 0
        else
            print_error ".env.example not found. Cannot create .env file."
            exit 1
        fi
    fi
}

# Start services
start_services() {
    print_info "Starting Video Merger API services..."
    docker-compose up -d
    
    print_info "Waiting for services to be healthy..."
    sleep 10
    
    if docker-compose ps | grep -q "Up"; then
        print_info "Services started successfully!"
        print_info "API is available at: http://localhost:8000"
        print_info "API Documentation: http://localhost:8000/api/docs (if enabled)"
        print_info "Check status with: ./deploy.sh status"
    else
        print_error "Failed to start services. Check logs with: ./deploy.sh logs"
        exit 1
    fi
}

# Stop services
stop_services() {
    print_info "Stopping Video Merger API services..."
    docker-compose down
    print_info "Services stopped successfully!"
}

# Restart services
restart_services() {
    print_info "Restarting Video Merger API services..."
    docker-compose restart
    print_info "Services restarted successfully!"
}

# Show logs
show_logs() {
    docker-compose logs -f --tail=100
}

# Show status
show_status() {
    print_info "Service Status:"
    docker-compose ps
    
    print_info "\nHealth Status:"
    
    # Check API health
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_info "API: Healthy ✓"
    else
        print_error "API: Unhealthy ✗"
    fi
    
    # Check Redis health
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        print_info "Redis: Healthy ✓"
    else
        print_error "Redis: Unhealthy ✗"
    fi
    
    # Show disk usage
    print_info "\nDisk Usage:"
    du -sh output/ logs/ temp/ 2>/dev/null || echo "No data yet"
}

# Cleanup old files
cleanup() {
    print_info "Cleaning up old files..."
    
    # Clean old output files (older than 24 hours)
    find output/ -name "*.mp4" -type f -mtime +1 -delete 2>/dev/null || true
    
    # Clean temp directory
    rm -rf temp/* 2>/dev/null || true
    
    # Clean old logs (older than 7 days)
    find logs/ -name "*.log" -type f -mtime +7 -delete 2>/dev/null || true
    
    print_info "Cleanup completed!"
}

# Backup data
backup() {
    print_info "Creating backup..."
    BACKUP_DIR="backups/backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup output files
    if [ -d output ] && [ "$(ls -A output)" ]; then
        cp -r output "$BACKUP_DIR/"
    fi
    
    # Backup logs
    if [ -d logs ] && [ "$(ls -A logs)" ]; then
        cp -r logs "$BACKUP_DIR/"
    fi
    
    # Backup .env
    if [ -f .env ]; then
        cp .env "$BACKUP_DIR/"
    fi
    
    print_info "Backup created at: $BACKUP_DIR"
}

# Update application
update() {
    print_info "Updating application..."
    
    # Pull latest code
    if [ -d .git ]; then
        git pull
    else
        print_warning "Not a git repository. Please update manually."
    fi
    
    # Rebuild containers
    docker-compose build --no-cache
    
    # Restart services
    docker-compose down
    docker-compose up -d
    
    print_info "Update completed!"
}

# Main script
main() {
    check_docker
    setup_directories
    
    case "${1:-}" in
        start)
            check_env
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        logs)
            show_logs
            ;;
        status)
            show_status
            ;;
        cleanup)
            cleanup
            ;;
        backup)
            backup
            ;;
        update)
            update
            ;;
        *)
            echo "Video Merger API Deployment Script"
            echo ""
            echo "Usage: $0 {start|stop|restart|logs|status|cleanup|backup|update}"
            echo ""
            echo "Commands:"
            echo "  start    - Start all services"
            echo "  stop     - Stop all services"
            echo "  restart  - Restart all services"
            echo "  logs     - Show service logs"
            echo "  status   - Show service status"
            echo "  cleanup  - Clean up old files"
            echo "  backup   - Backup important data"
            echo "  update   - Update and rebuild application"
            exit 1
            ;;
    esac
}

main "$@"
