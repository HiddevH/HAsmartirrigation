#!/bin/bash

# Smart Irrigation Deployment Script
# This script automates the entire deployment process to Docker container

set -e  # Exit on any error

# Configuration
CONTAINER_NAME="homeassistant-test"
FRONTEND_DIR="custom_components/smart_irrigation/frontend"
TARGET_DIR="/config/custom_components/smart_irrigation"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if container exists and is running
check_container() {
    if ! docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        print_error "Container '${CONTAINER_NAME}' is not running!"
        print_status "Available containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}"
        exit 1
    fi
}

# Function to build frontend
build_frontend() {
    print_status "Building frontend..."
    cd "${FRONTEND_DIR}"
    
    # Clean previous build
    if [ -d "dist" ]; then
        rm -rf dist/*
    fi
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        print_status "Installing npm dependencies..."
        npm install
    fi
    
    # Build
    npm run build
    
    if [ ! -f "dist/smart-irrigation.js" ]; then
        print_error "Build failed - dist/smart-irrigation.js not created"
        exit 1
    fi
    
    cd - > /dev/null
    print_success "Frontend built successfully"
}

# Function to deploy to container
deploy_to_container() {
    print_status "Deploying to container '${CONTAINER_NAME}'..."
    
    # Copy the entire custom_components directory
    docker cp custom_components/. "${CONTAINER_NAME}:${TARGET_DIR}/"
    
    print_success "Files copied to container"
}

# Function to restart Home Assistant
restart_homeassistant() {
    print_status "Restarting Home Assistant..."
    docker restart "${CONTAINER_NAME}"
    
    # Wait for container to be ready
    print_status "Waiting for Home Assistant to start..."
    sleep 5
    
    # Check if container is running
    if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        print_success "Home Assistant restarted successfully"
    else
        print_error "Failed to restart Home Assistant"
        exit 1
    fi
}

# Function to show browser cache clearing instructions
show_cache_instructions() {
    print_warning "🌐 IMPORTANT: Clear your browser cache to see changes!"
    echo ""
    echo -e "${YELLOW}Quick cache clearing options:${NC}"
    echo "  • Chrome/Edge: Ctrl+Shift+R (Cmd+Shift+R on Mac)"
    echo "  • Firefox: Ctrl+F5 (Cmd+Shift+R on Mac)"
    echo "  • Safari: Cmd+Option+R"
    echo "  • Or open DevTools (F12) → Right-click refresh → Empty Cache and Hard Reload"
    echo ""
    echo -e "${BLUE}Home Assistant URL:${NC} http://localhost:8123"
}

# Main deployment process
main() {
    echo "🚀 Smart Irrigation Deployment Script"
    echo "======================================"
    
    # Check if we're in the right directory
    if [ ! -f "custom_components/smart_irrigation/manifest.json" ]; then
        print_error "Please run this script from the root of the HAsmartirrigation repository"
        exit 1
    fi
    
    # Check container
    check_container
    
    # Build frontend
    build_frontend
    
    # Deploy to container
    deploy_to_container
    
    # Restart Home Assistant
    restart_homeassistant
    
    # Show cache clearing instructions
    show_cache_instructions
    
    print_success "🎉 Deployment completed successfully!"
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Smart Irrigation Deployment Script"
        echo ""
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --build-only   Only build frontend, don't deploy"
        echo "  --deploy-only  Only deploy (skip build)"
        echo ""
        echo "Default: Build frontend and deploy to Docker container"
        exit 0
        ;;
    --build-only)
        check_container
        build_frontend
        print_success "Build completed"
        ;;
    --deploy-only)
        check_container
        deploy_to_container
        restart_homeassistant
        show_cache_instructions
        print_success "Deployment completed"
        ;;
    "")
        main
        ;;
    *)
        print_error "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
