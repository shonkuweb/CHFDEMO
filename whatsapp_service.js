const express = require('express');
const cors = require('cors');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
const port = 3000;

app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

// Clean up stale Chromium lock files before starting
const authDir = path.join(__dirname, '.wwebjs_auth_v2');
if (fs.existsSync(authDir)) {
    try {
        function cleanLocks(dir) {
            if (!fs.existsSync(dir)) return;
            let files = [];
            try {
                files = fs.readdirSync(dir);
            } catch (e) {
                return;
            }
            for (const file of files) {
                const fullPath = path.join(dir, file);
                try {
                    if (['SingletonLock', 'SingletonCookie', 'SingletonSocket'].includes(file)) {
                        fs.unlinkSync(fullPath);
                        console.log(`Removed stale Chromium lock: ${fullPath}`);
                    } else {
                        const stat = fs.lstatSync(fullPath);
                        if (stat.isDirectory()) {
                            cleanLocks(fullPath);
                        }
                    }
                } catch (err) {
                    console.log(`Bypassed/Removed lock file ${fullPath}: ${err.message}`);
                    try {
                        fs.unlinkSync(fullPath);
                    } catch (_) {}
                }
            }
        }
        cleanLocks(authDir);
    } catch (e) {
        console.error('Failed to clean up lock files:', e);
    }
}

let qrDataUrl = null;
let isReady = false;
let isInitializing = false;
let client = null;

function resetAndReinitializeSession() {
    console.log('Resetting WhatsApp session and clearing auth files...');
    isReady = false;
    isInitializing = false;
    qrDataUrl = null;
    if (client) {
        try { client.destroy(); } catch (e) {}
        client = null;
    }
    const sessionDir = path.join(authDir, 'session-whatsapp-client-v2');
    if (fs.existsSync(sessionDir)) {
        try {
            fs.rmSync(sessionDir, { recursive: true, force: true });
            console.log('Cleaned up session directory for fresh QR code generation.');
        } catch (e) {
            console.error('Failed to clean session directory:', e);
        }
    }
    setTimeout(() => {
        initializeWhatsAppClient();
    }, 1500);
}

function initializeWhatsAppClient() {
    if (isInitializing) return;
    isInitializing = true;
    console.log('Initializing WhatsApp Client...');
    
    if (client) {
        try { client.destroy(); } catch (e) {}
        client = null;
    }

    // Auto-recovery watchdog: if no QR or Ready within 25 seconds, clear stale session and retry
    let watchdogTimer = setTimeout(() => {
        if (!isReady && !qrDataUrl) {
            console.warn('WhatsApp client initialization timed out without QR or Ready. Forcing session reset...');
            resetAndReinitializeSession();
        }
    }, 25000);

    // Setup LocalAuth to persist session so we don't have to scan every time
    client = new Client({
        authStrategy: new LocalAuth({ clientId: 'whatsapp-client-v2', dataPath: './.wwebjs_auth_v2' }),
        webVersionCache: {
            type: 'remotePath',
            remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1018923055-alpha.html'
        },
        userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        puppeteer: {
            headless: true,
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--disable-gpu',
                '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
            ]
        }
    });

    client.on('qr', async (qr) => {
        console.log('New WhatsApp QR Code generated. Scan to log in.');
        if (watchdogTimer) clearTimeout(watchdogTimer);
        try {
            qrDataUrl = await qrcode.toDataURL(qr, {
                margin: 2,
                scale: 8,
                color: {
                    dark: '#000000',
                    light: '#ffffff'
                }
            });
            isReady = false;
            isInitializing = false;
        } catch (err) {
            console.error('Error generating QR code data URL:', err);
        }
    });

    client.on('ready', () => {
        console.log('WhatsApp Client is ready!');
        if (watchdogTimer) clearTimeout(watchdogTimer);
        isReady = true;
        isInitializing = false;
        qrDataUrl = null;
    });

    client.on('authenticated', () => {
        console.log('WhatsApp Client authenticated!');
        if (watchdogTimer) clearTimeout(watchdogTimer);
    });

    client.on('auth_failure', msg => {
        console.error('Authentication failure', msg);
        if (watchdogTimer) clearTimeout(watchdogTimer);
        resetAndReinitializeSession();
    });

    client.on('disconnected', (reason) => {
        console.log('WhatsApp Client was disconnected', reason);
        if (watchdogTimer) clearTimeout(watchdogTimer);
        resetAndReinitializeSession();
    });

    client.initialize().catch(err => {
        console.error('Failed to initialize WhatsApp client:', err);
        if (watchdogTimer) clearTimeout(watchdogTimer);
        isInitializing = false;
        isReady = false;
        qrDataUrl = null;
    });
}

initializeWhatsAppClient();

// API Endpoints

app.get('/api/whatsapp/status', (req, res) => {
    res.json({
        ready: isReady,
        qr: qrDataUrl
    });
});

app.post('/api/whatsapp/send', async (req, res) => {
    if (!isReady) {
        return res.status(400).json({ error: 'WhatsApp client is not ready. Please scan the QR code first.' });
    }

    const { number, message, pdf_base64, filename } = req.body;

    if (!number) {
        return res.status(400).json({ error: 'Phone number is required.' });
    }

    try {
        // Strip any non-numeric characters from the number
        let cleanNumber = number.replace(/\D/g, '');
        
        // If it's a 10-digit number (common in India), prepend '91'
        if (cleanNumber.length === 10) {
            cleanNumber = '91' + cleanNumber;
        }

        // Format number to WhatsApp JID (@c.us)
        let chatId = `${cleanNumber}@c.us`;
        
        // Use getNumberId to get official WhatsApp JID & verify registration
        try {
            const numberDetails = await client.getNumberId(cleanNumber);
            if (numberDetails && numberDetails._serialized) {
                chatId = numberDetails._serialized;
            } else {
                console.warn(`getNumberId did not find registered ID for ${cleanNumber}, using fallback ${chatId}`);
            }
        } catch (numErr) {
            console.warn(`getNumberId check bypassed for ${cleanNumber}:`, numErr.message);
        }
        
        if (pdf_base64) {
            const cleanBase64 = pdf_base64.includes(',') ? pdf_base64.split(',')[1] : pdf_base64;
            const mediaName = filename || 'Plant_Experience_Centre_Invoice.pdf';
            const media = new MessageMedia('application/pdf', cleanBase64, mediaName);
            const options = { caption: message || '', sendMediaAsDocument: true };
            const response = await client.sendMessage(chatId, media, options);
            console.log(`WhatsApp PDF invoice successfully sent to ${chatId}`);
            return res.json({ success: true, messageId: response.id ? response.id._serialized : null });
        } else {
            const response = await client.sendMessage(chatId, message);
            console.log(`WhatsApp text message successfully sent to ${chatId}`);
            return res.json({ success: true, messageId: response.id ? response.id._serialized : null });
        }
    } catch (error) {
        console.error('Error sending message:', error);
        const errMsg = error.message || error.toString();
        res.status(500).json({ error: `Failed to send message on WhatsApp: ${errMsg}`, details: error.toString() });
    }
});

app.post('/api/whatsapp/logout', async (req, res) => {
    try {
        console.log('Logging out / resetting WhatsApp session...');
        if (client) {
            try { await client.logout(); } catch (e) { console.warn('Logout warning:', e.message); }
            try { await client.destroy(); } catch (e) { console.warn('Destroy warning:', e.message); }
        }
        isReady = false;
        qrDataUrl = null;
        client = null;

        // Reset persistent session data directory if exists to force fresh QR pairing
        try {
            const sessionDir = path.join(authDir, 'session-whatsapp-client-v2');
            if (fs.existsSync(sessionDir)) {
                fs.rmSync(sessionDir, { recursive: true, force: true });
            }
        } catch (e) {
            console.warn('Session dir cleanup warning:', e.message);
        }

        // Reinitialize the client after a short delay
        setTimeout(() => {
            initializeWhatsAppClient();
        }, 1500);

        return res.json({ success: true, message: 'Logged out and session reset successfully.' });
    } catch (error) {
        console.error('Error logging out:', error);
        isReady = false;
        qrDataUrl = null;
        client = null;
        setTimeout(() => {
            initializeWhatsAppClient();
        }, 1500);
        return res.json({ success: true, message: 'Session reset complete.' });
    }
});

app.listen(port, () => {
    console.log(`WhatsApp Microservice running at http://localhost:${port}`);
});
