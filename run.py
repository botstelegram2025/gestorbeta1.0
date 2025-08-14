#!/usr/bin/env python3
"""
Alternative run script for deployment compatibility
This script can be used as a fallback if app.py isn't executed properly
Automatically detects environment and uses appropriate server
"""

import os
import sys
import subprocess

def run_with_gunicorn():
    """Run with Gunicorn for production"""
    port = os.getenv('PORT', '5000')
    cmd = [
        'gunicorn',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '1',
        '--timeout', '120',
        '--access-logfile', '-',
        '--error-logfile', '-',
        'wsgi:app'
    ]
    print(f"Starting with Gunicorn on port {port}")
    subprocess.run(cmd)

def run_with_flask():
    """Run with Flask development server"""
    try:
        from app import app
        
        port = int(os.getenv('PORT', 5000))
        host = os.getenv('HOST', '0.0.0.0')
        
        print(f"Starting Flask development server on {host}:{port}")
        app.run(host=host, port=port, debug=False, threaded=True)
        
    except Exception as e:
        print(f"Error starting Flask application: {e}")
        sys.exit(1)

def main():
    """Main entry point - auto-detects environment"""
    # Check if we're in production environment
    is_production = (
        os.getenv('PORT') is not None or 
        os.getenv('ENVIRONMENT') == 'production' or 
        os.getenv('NODE_ENV') == 'production'
    )
    
    if is_production:
        print("Production environment detected")
        run_with_gunicorn()
    else:
        print("Development environment detected")
        run_with_flask()

if __name__ == '__main__':
    main()