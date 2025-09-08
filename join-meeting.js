const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

class MeetingRecorder {
    constructor() {
        this.browser = null;
        this.page = null;
        this.isRecording = false;
        this.recordingPath = './recordings';
        
        // Создаем папку для записей если не существует
        if (!fs.existsSync(this.recordingPath)) {
            fs.mkdirSync(this.recordingPath, { recursive: true });
        }
    }

    async init() {
        console.log('🚀 Запуск браузера...');
        
        this.browser = await puppeteer.launch({
            headless: true, // Запускаем в headless режиме
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
                '--disable-features=VizDisplayCompositor'
            ]
        });

        this.page = await this.browser.newPage();
        
        // Настраиваем разрешение
        await this.page.setViewport({ width: 1366, height: 768 });
        
        // Даем разрешения на микрофон и камеру
        const context = this.browser.defaultBrowserContext();
        await context.overridePermissions('https://meet.google.com', ['microphone', 'camera']);
        await context.overridePermissions('https://zoom.us', ['microphone', 'camera']);
        await context.overridePermissions('https://teams.microsoft.com', ['microphone', 'camera']);
        
        console.log('✅ Браузер готов');
    }

    async joinGoogleMeet(meetingUrl, userName = 'Meeting Bot') {
        console.log('📞 Подключение к Google Meet:', meetingUrl);
        
        try {
            await this.page.goto(meetingUrl, { 
                waitUntil: 'networkidle2',
                timeout: 30000 
            });
            
            // Ждем загрузки страницы
            await this.page.waitForTimeout(3000);
            
            // Вводим имя если необходимо
            try {
                await this.page.waitForSelector('input[placeholder*="имя" i], input[placeholder*="name" i]', { timeout: 5000 });
                await this.page.type('input[placeholder*="имя" i], input[placeholder*="name" i]', userName);
                console.log('✅ Имя введено');
            } catch (e) {
                console.log('ℹ️ Поле имени не найдено, пропускаем');
            }
            
            // Отключаем микрофон и камеру
            try {
                // Кнопка микрофона
                await this.page.click('[data-is-muted="false"]');
                console.log('🔇 Микрофон отключен');
            } catch (e) {
                console.log('ℹ️ Кнопка микрофона не найдена');
            }
            
            try {
                // Кнопка камеры
                await this.page.click('[data-is-video-muted="false"]');
                console.log('📹 Камера отключена');
            } catch (e) {
                console.log('ℹ️ Кнопка камеры не найдена');
            }
            
            // Нажимаем "Присоединиться"
            const joinSelectors = [
                '[data-mdc-dialog-action="ok"]',
                'button[jsname="Qx7uuf"]',
                'span:contains("Присоединиться")',
                'span:contains("Join now")',
                '.NPEfkd',
                '[data-promo-anchor-id="start_call"]'
            ];
            
            let joined = false;
            for (const selector of joinSelectors) {
                try {
                    await this.page.waitForSelector(selector, { timeout: 2000 });
                    await this.page.click(selector);
                    console.log('✅ Нажата кнопка присоединения');
                    joined = true;
                    break;
                } catch (e) {
                    continue;
                }
            }
            
            if (!joined) {
                // Пробуем через текст
                await this.page.evaluate(() => {
                    const buttons = Array.from(document.querySelectorAll('button, span, div'));
                    const joinButton = buttons.find(btn => 
                        btn.textContent.includes('Присоединиться') || 
                        btn.textContent.includes('Join') ||
                        btn.textContent.includes('Войти')
                    );
                    if (joinButton) joinButton.click();
                });
            }
            
            // Ждем подключения к встрече
            await this.page.waitForTimeout(5000);
            console.log('✅ Успешно подключились к встрече');
            
            return true;
            
        } catch (error) {
            console.error('❌ Ошибка при подключении к Meet:', error.message);
            return false;
        }
    }

    async joinZoomMeeting(meetingUrl, meetingId, passcode = '') {
        console.log('📞 Подключение к Zoom:', meetingUrl);
        
        try {
            await this.page.goto(meetingUrl, { 
                waitUntil: 'networkidle2',
                timeout: 30000 
            });
            
            // Вводим Meeting ID если нужно
            if (meetingId) {
                try {
                    await this.page.type('#meeting-id-input', meetingId);
                    await this.page.click('#join-btn');
                } catch (e) {
                    console.log('ℹ️ Поле Meeting ID не найдено');
                }
            }
            
            // Вводим пароль если нужно
            if (passcode) {
                try {
                    await this.page.waitForSelector('input[type="password"]', { timeout: 5000 });
                    await this.page.type('input[type="password"]', passcode);
                    await this.page.click('button[type="submit"]');
                } catch (e) {
                    console.log('ℹ️ Поле пароля не найдено');
                }
            }
            
            // Нажимаем "Join from browser"
            try {
                await this.page.waitForSelector('a[href*="wc/join"]', { timeout: 10000 });
                await this.page.click('a[href*="wc/join"]');
            } catch (e) {
                console.log('ℹ️ Кнопка "Join from browser" не найдена');
            }
            
            await this.page.waitForTimeout(5000);
            console.log('✅ Успешно подключились к Zoom');
            
            return true;
            
        } catch (error) {
            console.error('❌ Ошибка при подключении к Zoom:', error.message);
            return false;
        }
    }

    async startRecording(duration = 3600) { // 1 час по умолчанию
        console.log('🎥 Начинаем запись...');
        
        this.isRecording = true;
        const timestamp = new Date().toISOString().replace(/:/g, '-').split('.')[0];
        const audioFile = path.join(this.recordingPath, `meeting_${timestamp}.webm`);
        
        try {
            // Начинаем запись аудио
            await this.page.evaluate(() => {
                return new Promise((resolve) => {
                    navigator.mediaDevices.getDisplayMedia({
                        audio: true,
                        video: false
                    }).then(stream => {
                        window.mediaRecorder = new MediaRecorder(stream);
                        window.recordedChunks = [];
                        
                        window.mediaRecorder.ondataavailable = (event) => {
                            if (event.data.size > 0) {
                                window.recordedChunks.push(event.data);
                            }
                        };
                        
                        window.mediaRecorder.start();
                        resolve();
                    }).catch(err => {
                        console.error('Ошибка захвата аудио:', err);
                        resolve();
                    });
                });
            });
            
            console.log('✅ Запись началась');
            
            // Записываем указанное время
            setTimeout(() => {
                this.stopRecording();
            }, duration * 1000);
            
            return audioFile;
            
        } catch (error) {
            console.error('❌ Ошибка начала записи:', error.message);
            return null;
        }
    }

    async stopRecording() {
        if (!this.isRecording) return null;
        
        console.log('⏹️ Останавливаем запись...');
        
        try {
            const audioData = await this.page.evaluate(() => {
                return new Promise((resolve) => {
                    if (window.mediaRecorder && window.mediaRecorder.state !== 'inactive') {
                        window.mediaRecorder.onstop = () => {
                            const blob = new Blob(window.recordedChunks, { type: 'audio/webm' });
                            const reader = new FileReader();
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        };
                        window.mediaRecorder.stop();
                    } else {
                        resolve(null);
                    }
                });
            });
            
            if (audioData) {
                const timestamp = new Date().toISOString().replace(/:/g, '-').split('.')[0];
                const audioFile = path.join(this.recordingPath, `meeting_${timestamp}.webm`);
                
                // Сохраняем файл
                const base64Data = audioData.replace(/^data:audio\/webm;base64,/, '');
                fs.writeFileSync(audioFile, base64Data, 'base64');
                
                console.log('✅ Запись сохранена:', audioFile);
                this.isRecording = false;
                return audioFile;
            }
            
        } catch (error) {
            console.error('❌ Ошибка остановки записи:', error.message);
        }
        
        this.isRecording = false;
        return null;
    }

    async leaveMeeting() {
        console.log('👋 Покидаем встречу...');
        
        try {
            // Ищем кнопку "Покинуть" или "Leave"
            const leaveSelectors = [
                '[data-tooltip*="Покинуть"]',
                '[data-tooltip*="Leave"]',
                'button[data-mdc-dialog-action="ok"]',
                '.VfPpkd-Bz112c-LgbsSe[jsname="h5Jlkc"]'
            ];
            
            for (const selector of leaveSelectors) {
                try {
                    await this.page.click(selector);
                    console.log('✅ Нажата кнопка выхода');
                    break;
                } catch (e) {
                    continue;
                }
            }
            
            await this.page.waitForTimeout(2000);
            
        } catch (error) {
            console.error('❌ Ошибка при выходе из встречи:', error.message);
        }
    }

    async close() {
        console.log('🔄 Закрываем браузер...');
        
        if (this.isRecording) {
            await this.stopRecording();
        }
        
        if (this.browser) {
            await this.browser.close();
        }
        
        console.log('✅ Браузер закрыт');
    }

    // Утилита для получения текста с страницы (для транскрипции чата)
    async getChatMessages() {
        try {
            const messages = await this.page.evaluate(() => {
                const chatMessages = document.querySelectorAll('[data-message-text], .chat-message, .message-content');
                return Array.from(chatMessages).map(msg => msg.textContent.trim()).filter(text => text.length > 0);
            });
            
            return messages;
        } catch (error) {
            console.error('❌ Ошибка получения сообщений чата:', error.message);
            return [];
        }
    }
}

// Экспорт для использования в Python
module.exports = MeetingRecorder;

// Если файл запускается напрямую
if (require.main === module) {
    const recorder = new MeetingRecorder();
    
    async function testMeeting() {
        await recorder.init();
        
        // Пример использования
        const meetingUrl = process.argv[2] || 'https://meet.google.com/test-meeting';
        const duration = parseInt(process.argv[3]) || 60; // 1 минута для теста
        
        console.log(`🎯 Тест: подключение к ${meetingUrl} на ${duration} секунд`);
        
        try {
            const joined = await recorder.joinGoogleMeet(meetingUrl, 'Test Bot');
            
            if (joined) {
                const recordingFile = await recorder.startRecording(duration);
                
                // Ждем окончания записи
                setTimeout(async () => {
                    await recorder.leaveMeeting();
                    await recorder.close();
                    console.log('🎉 Тест завершен!');
                    process.exit(0);
                }, (duration + 5) * 1000);
            } else {
                console.log('❌ Не удалось подключиться к встрече');
                await recorder.close();
                process.exit(1);
            }
            
        } catch (error) {
            console.error('❌ Ошибка в тесте:', error.message);
            await recorder.close();
            process.exit(1);
        }
    }
    
    testMeeting();
}