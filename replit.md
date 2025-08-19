# Bot de Gestão de Clientes WhatsApp/Telegram

## Overview
This project is a client management system designed to automate communication for small businesses. It integrates a bot for Telegram and the Baileys API for WhatsApp, enabling client registration, message template management, automatic billing scheduling, and personalized message sending. The goal is to optimize client communication, especially for billing and support, providing a scalable and production-ready solution for automated client management. This includes a multi-tenant system with user registration, subscriptions via Mercado Pago PIX, and robust data isolation to ensure each user sees only their own data.

## User Preferences
Preferred communication style: Simple, everyday language.
Message automation: Only send automatic collection messages to clients overdue by exactly 1 day. Clients overdue by more than 1 day should not receive automatic messages.
Daily verification: System checks all clients at 9 AM daily and processes messages immediately for same-day sending.
Auto-cancellation: When a client is renewed, all pending messages for that client are automatically cancelled from the queue.
Search interface: Client search results should use the same format as client listing - inline buttons with individual actions for each client found, including status indicators and complete navigation options.
Button display format: Client buttons throughout the system display "name + expiration date" format instead of "name + ID" for better usability.
Phone number format: All phone numbers are automatically standardized to Baileys WhatsApp format (DDD12345678 - 10 digits total) regardless of input format. Modern 9-digit numbers have the first 9 removed for Baileys compatibility.
Renewal behavior: When renewing clients, system now asks if user wants to send renewal message. Date calculation fixed to maintain same day of next month (e.g., Aug 15 -> Sep 15) instead of adding exactly 30 days.
Cache behavior: Client list updates immediately after any edit operation. System automatically invalidates cache when client data is modified to ensure real-time data display.
Template protection: System templates (chat_id_usuario = NULL) cannot be edited by users. Only custom user templates can be modified.
User validation: Automatic messages only sent when valid chat_id_usuario is present, preventing orphaned messages.
QR code persistence: WhatsApp sessions automatically saved to PostgreSQL and restored on Railway deploys, eliminating need to re-scan QR codes after updates.
Daily alerts isolation: Daily verification alerts and automatic message processing now fully isolated by user - each user receives only their own client data and alerts.
Hybrid scheduling system: System uses global schedules for efficiency but detects and logs individual user preferences. Data processing completely isolated by user while maintaining centralized timing for optimal resource usage.
TEMPLATE SELECTION FILTER FIX: Enhanced template filtering for message sending to show only user-created templates. Fixed enviar_mensagem_cliente function to filter out system default templates when users click "Send Message", ensuring complete security and improved UX. Updated all renewal functions to only search for user-created renewal templates. System now guarantees users see only their own personalized templates during message selection, hiding system defaults for security.
PERSONALIZED SCHEDULING SYSTEM FIXED: Critical bug in personalized scheduling system completely resolved (19/08/2025). Fixed conversation state handling that was causing bot to become unresponsive when users attempted to change notification times. Implemented proper database isolation for user-specific schedule configurations with direct SQL operations bypassing problematic ORM constraints. Enhanced schedule_config.py with robust error handling and immediate state cleanup. Users can now safely customize notification times (e.g., 16:52) without system freezing. All schedule modification functions properly isolated by chat_id_usuario ensuring multi-tenant security.
SEQUENTIAL SCHEDULING ENHANCEMENT: Added advanced sequential scheduling capabilities allowing users to configure separate verification and sending times (19/08/2025). Users can now set verification at 18:00 to detect expired clients and automatic sending at 18:10 for optimal business hour notifications. Enhanced schedule_config.py with sequential timing recommendations and improved UI for better user experience in scheduling configuration.

## System Architecture

### Core Components
-   **Bot Framework**: Utilizes `python-telegram-bot` for an administrative interface via Telegram, supporting conversational states for CRUD operations.
-   **WhatsApp Integration**: Integrates with the Baileys API for automated WhatsApp message sending, including retry mechanisms, status caching, and rate limiting. Features QR code generation for connection, real-time status monitoring, comprehensive logging, and persistent session storage in PostgreSQL for seamless reconnection. Supports unlimited simultaneous user sessions with isolated `user_{chat_id}` sessions and dedicated authentication folders.
-   **Database Layer**: PostgreSQL serves as the primary database, managing tables for clients, templates, send logs, message queues, and WhatsApp session persistence. Uses `psycopg2` with `RealDictCursor`. Includes comprehensive multi-tenant isolation with `chat_id_usuario` columns and foreign key relationships.
-   **Advanced Template System**: A comprehensive template system supports dynamic variables (e.g., `{nome}`, `{vencimento}`) with interactive management, usage statistics, and pre-built template models for different business scenarios (welcome messages, billing reminders, expiry notifications). Includes a 5-step creation workflow with type selection and ready-to-copy professional templates. Template variables (empresa_nome, empresa_telefone, empresa_email, pix_chave, pix_beneficiario, suporte_telefone, suporte_email) are fully functional with substitution, multi-tenant isolation, and fallback values.
-   **Scheduler System**: `APScheduler` is used for scheduling recurring tasks like daily expiration checks and message queue processing, configured for consistent timezone (America/Sao_Paulo) and thread-safe operations. Features daily verification to add only same-day messages to queue and automatic message cancellation when clients are renewed.
-   **Configuration Management**: A centralized system manages configurations via environment variables, with typed classes and automatic validation, providing an interactive interface for global settings.
-   **Error Handling**: Implements structured logging and specific error handling for external API network issues with exponential retry.
-   **Deployment**: Uses Flask for a web server (`app.py`), configured for Cloud Run with health and status endpoints, supporting WSGI with Gunicorn for production. The bot can run in webhook or polling mode.

### Key Features
-   **Client Management**: Provides a complete registration flow, CRUD operations, and displays clients with visual statuses and individual actions. It supports multiple plans per phone number and individual notification preferences per client. Enhanced client renewal process offers choice between maintaining same expiration date or setting custom renewal date.
-   **Advanced Template Management**: Interactive management with comprehensive template creation system featuring 8 specialized types (Welcome, 2 days before expiry, 1 day before expiry, expiry day, 1 day after expired, general billing, renewal, custom). Each type includes professional template models ready for immediate use or customization. 5-step creation process with type selection, model preview, editing capabilities, and confirmation workflow.
-   **Configuration System**: An interactive interface for managing global configurations such as company data, PIX settings, and WhatsApp API status. Direct shortcuts for "Agendador" and "Templates" in settings for improved UX.
-   **Message Sending**: Supports both manual and automated message sending, with message preview and automatic variable substitution, and a user-controlled renewal message flow. Messages are only added to queue on their intended send date. Individual client notification preferences control automated message delivery.
-   **Reporting System**: Offers comprehensive period-based reports (7 days, 30 days, 3 months, 6 months) including financial analysis, client statistics, performance metrics, and monthly comparisons. Includes financial summary on client listing showing expected, received, and overdue amounts. All reports properly initialize with zero values for new users.
-   **Multi-User System**: Supports user registration with a free trial, monthly subscriptions via Mercado Pago PIX, automatic access control (admin vs. subscriber), and a user onboarding flow. Includes multi-tenant data isolation to prevent users from accessing or modifying other users' data.
-   **UI/UX Decisions**: Bot-based interfaces (Telegram) utilize interactive keyboards, inline buttons, emojis for status indicators, and dynamic messages for intuitive navigation and feedback. Client information is displayed with single-touch copyable text sections using formatted code blocks. "Meus Clientes" button changed to "Gestão de Clientes" for non-admin users to provide complete client management functionality.

## External Dependencies

-   **PostgreSQL Database**: The primary database for all system data persistence.
-   **Telegram Bot API**: Used via the `python-telegram-bot` library for the bot's administrative interface and functionalities.
-   **Baileys WhatsApp API**: An external integration for programmatic WhatsApp message sending, managed by a Node.js server.
-   **Mercado Pago API**: Used for PIX payment processing and subscription management.
-   **APScheduler**: Python library for scheduling and executing background tasks.
-   **Python Libraries**:
    -   `psycopg2`: PostgreSQL adapter.
    -   `pytz`: For timezone manipulation.
    -   `qrcode`: For generating QR codes (used for WhatsApp authentication).
    -   `requests`: For general HTTP communication with external APIs.