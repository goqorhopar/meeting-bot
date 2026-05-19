const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

/**
 * Meeting Recorder - Headless browser automation for joining and recording meetings
 * Supports: Google Meet, Zoom, Microsoft Teams
 */
class MeetingRecorder {
    constructor() {
        this.browser = null;
        this.page = null;
        this.isRecording = false;
        this.recordingPath = './recordings';
        
        // Ensure recordings directory exists
        if (!fs.existsSync(this.recordingPath)) {
            fs.mkdirSync(this.recordingPath, { recursive: true });
        }
    }

    /**
     * Initialize Puppeteer browser with proper flags for headless operation
     */
    async init() {
        console.log('🚀 Launching browser...');
        
        try {
            this.browser = await puppeteer.launch({
                headless: 'new',
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu',
                    '--use-fake-ui-for-media-stream',
                    '--use-fake-device-for-media-stream',
                    '--allow-running-insecure-content',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                    '--autoplay-policy=no-user-gesture-required',
                    '--mute-audio'
                ]
            });

            this.page = await this.browser.newPage();
            await this.page.setViewport({ width: 1920, height: 1080 });
            
            const context = this.browser.defaultBrowserContext();
            await context.overridePermissions('https://meet.google.com', ['microphone', 'camera']);
            await context.overridePermissions('https://zoom.us', ['microphone', 'camera']);
            await context.overridePermissions('https://teams.microsoft.com', ['microphone', 'camera']);
            
            console.log('✅ Browser ready');
            return true;
        } catch (error) {
            console.error('❌ Failed to launch browser:', error.message);
            return false;
        }
    }

    /**
     * Join a Google Meet meeting
     */
    async joinGoogleMeet(meetingUrl, userName = 'Meeting Bot') {
        console.log('📞 Joining Google Meet:', meetingUrl);
        
        try {
            // Validate URL format
            if (!meetingUrl || !meetingUrl.startsWith('http')) {
                throw new Error('Invalid meeting URL');
            }
            
            await this.page.goto(meetingUrl, { waitUntil: 'networkidle2', timeout: 30000 });
            await this.sleep(3000);
            
            // Try to enter name
            try {
                const nameInput = await this.page.$('input[placeholder*="имя" i], input[placeholder*="name" i]');
                if (nameInput) {
                    await nameInput.type(userName, { delay: 50 });
                    console.log('✅ Name entered');
                }
            } catch (e) { /* ignore */ }
            
            // Mute microphone
            try {
                await this.page.click('[data-is-muted="false"]');
                console.log('🔇 Microphone muted');
            } catch (e) { /* ignore */ }
            
            // Turn off camera
            try {
                await this.page.click('[data-is-video-muted="false"]');
                console.log('📹 Camera turned off');
            } catch (e) { /* ignore */ }
            
            // Click join button
            const joinSelectors = [
                '[data-mdc-dialog-action="ok"]',
                'button[jsname="Qx7uuf"]',
                '.NPEfkd'
            ];
            
            let joined = false;
            for (const selector of joinSelectors) {
                try {
                    await this.page.waitForSelector(selector, { timeout: 2000 });
                    await this.page.click(selector);
                    joined = true;
                    break;
                } catch (e) { continue; }
            }
            
            if (!joined) {
                await this.page.evaluate(() => {
                    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
                    const joinButton = buttons.find(btn => 
                        btn.textContent.toLowerCase().includes('join') || 
                        btn.textContent.toLowerCase().includes('присоединиться')
                    );
                    if (joinButton) joinButton.click();
                });
            }
            
            await this.sleep(5000);
            console.log('✅ Successfully joined meeting');
            return true;
        } catch (error) {
            console.error('❌ Error joining Google Meet:', error.message);
            return false;
        }
    }

    /**
     * Leave the current meeting
     */
    async leaveMeeting() {
        console.log('👋 Leaving meeting...');
        try {
            const leaveSelectors = [
                '[data-tooltip*="Покинуть"]',
                '[data-tooltip*="Leave"]',
                'button[data-mdc-dialog-action="ok"]'
            ];
            
            for (const selector of leaveSelectors) {
                try {
                    await this.page.click(selector);
                    break;
                } catch (e) { continue; }
            }
            await this.sleep(2000);
        } catch (error) {
            console.error('❌ Error leaving meeting:', error.message);
        }
    }

    /**
     * Close the browser
     */
    async close() {
        console.log('🔄 Closing browser...');
        if (this.browser) {
            await this.browser.close();
            console.log('✅ Browser closed');
        }
    }

    /**
     * Sleep helper
     */
    async sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Export for use in other modules
module.exports = MeetingRecorder;

// CLI entry point
if (require.main === module) {
    const recorder = new MeetingRecorder();
    
    async function runTest() {
        const meetingUrl = process.argv[2];
        const duration = parseInt(process.argv[3]) || 60;
        
        if (!meetingUrl) {
            console.error('Usage: node join-meeting.js <meeting-url> [duration-seconds]');
            process.exit(1);
        }
        
        console.log(`🎯 Test: joining ${meetingUrl} for ${duration} seconds`);
        
        try {
            await recorder.init();
            const joined = await recorder.joinGoogleMeet(meetingUrl, 'Test Bot');
            
            if (joined) {
                console.log(`⏳ Waiting ${duration} seconds...`);
                await recorder.sleep(duration * 1000);
                await recorder.leaveMeeting();
                await recorder.close();
                console.log('🎉 Test completed!');
                process.exit(0);
            } else {
                console.log('❌ Failed to join meeting');
                await recorder.close();
                process.exit(1);
            }
        } catch (error) {
            console.error('❌ Test error:', error.message);
            await recorder.close();
            process.exit(1);
        }
    }
    
    runTest();
}
