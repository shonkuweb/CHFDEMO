const express = require('express');
const cors = require('cors');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
const port = 3000;

app.use(cors());
app.use(express.json());

// Clean up stale Chromium lock files before starting
const authDir = path.join(__dirname, '.wwebjs_auth_v2');
if (fs.existsSync(authDir)) {
    try {
        function cleanLocks(dir) {
            const files = fs.readdirSync(dir);
            for (const file of files) {
                const fullPath = path.join(dir, file);
                const stat = fs.statSync(fullPath);
                if (stat.isDirectory()) {
                    cleanLocks(fullPath);
                } else if (['SingletonLock', 'SingletonCookie', 'SingletonSocket'].includes(file)) {
                    fs.unlinkSync(fullPath);
                    console.log(`Removed stale Chromium lock: ${fullPath}`);
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
let client = null;

function initializeWhatsAppClient() {
    console.log('Initializing WhatsApp Client...');
    
    // Setup LocalAuth to persist session so we don't have to scan every time
    client = new Client({
        authStrategy: new LocalAuth({ clientId: 'whatsapp-client-v2', dataPath: './.wwebjs_auth_v2' }),
        webVersionCache: { type: 'local' },
        puppeteer: {
            headless: true,
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || null,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu'
            ]
        }
    });

    client.on('qr', async (qr) => {
        console.log('QR Code generated. Scan to log in.');
        try {
            qrDataUrl = await qrcode.toDataURL(qr);
            isReady = false;
        } catch (err) {
            console.error('Error generating QR code data URL', err);
        }
    });

    client.on('ready', () => {
        console.log('WhatsApp Client is ready!');
        isReady = true;
        qrDataUrl = null;
    });

    client.on('authenticated', () => {
        console.log('WhatsApp Client authenticated!');
    });

    client.on('auth_failure', msg => {
        console.error('Authentication failure', msg);
        isReady = false;
        qrDataUrl = null;
    });

    client.on('disconnected', (reason) => {
        console.log('WhatsApp Client was disconnected', reason);
        isReady = false;
        qrDataUrl = null;
        // Re-initialize client on disconnect
        setTimeout(initializeWhatsAppClient, 5000);
    });

    client.initialize();
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

    const { number, message } = req.body;

    if (!number || !message) {
        return res.status(400).json({ error: 'Phone number and message are required.' });
    }

    try {
        // Strip any non-numeric characters from the number
        let cleanNumber = number.replace(/\D/g, '');
        
        // If it's a 10-digit number (common in India), prepend '91'
        if (cleanNumber.length === 10) {
            cleanNumber = '91' + cleanNumber;
        }

        const chatId = `${cleanNumber}@c.us`;
        
        // Check if the number is registered on WhatsApp
        const registered = await client.isRegisteredUser(chatId);
        if (!registered) {
            return res.status(400).json({ error: `The number ${cleanNumber} is not registered on WhatsApp.` });
        }
        
        const response = await client.sendMessage(chatId, message);
        res.json({ success: true });
    } catch (error) {
        console.error('Error sending message:', error);
        res.status(500).json({ error: 'Failed to send message on WhatsApp. Make sure your phone is connected.', details: error.toString() });
    }
});

app.post('/api/whatsapp/logout', async (req, res) => {
    try {
        if (client) {
            console.log('Logging out of WhatsApp...');
            try { await client.logout(); } catch (e) { console.error(e); }
            try { await client.destroy(); } catch (e) { console.error(e); }
            isReady = false;
            qrDataUrl = null;
            client = null;
            
            // Reinitialize the client after a short delay
            setTimeout(() => {
                initializeWhatsAppClient();
            }, 3000);
            
            res.json({ success: true, message: 'Logged out successfully.' });
        } else {
            res.status(400).json({ error: 'Client not initialized.' });
        }
    } catch (error) {
        console.error('Error logging out:', error);
        res.status(500).json({ error: 'Failed to log out.', details: error.toString() });
    }
});

app.listen(port, () => {
    console.log(`WhatsApp Microservice running at http://localhost:${port}`);
});
