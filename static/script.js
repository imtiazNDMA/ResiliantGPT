
document.addEventListener('DOMContentLoaded', function () {
    const chatOutput = document.getElementById('chat-output');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const newChatBtn = document.getElementById('new-chat-btn');
    const chatHistorySidebar = document.getElementById('chat-history-sidebar');
    const uploadBtn = document.getElementById('upload-btn');
    const fileUpload = document.getElementById('file-upload');

    let currentConversationId = null;
    let currentMode = 'pakistan'; // Default to pakistan for backend compatibility

    initializeChat();

    sendButton.addEventListener('click', sendMessage);
    newChatBtn.addEventListener('click', createNewChat);
    uploadBtn.addEventListener('click', () => fileUpload.click());
    fileUpload.addEventListener('change', handleFileUpload);

    userInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    userInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') this.style.height = '';
    });



    async function handleFileUpload(event) {
        const files = event.target.files;
        if (!files || files.length === 0) {
            addMessage('system', 'Please select at least one file');
            return;
        }

        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }
        formData.append('mode', currentMode);

        try {
            addMessage('system', `Learning from ${files.length} document(s)...`);

            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || result.message || 'Learning failed');
            }

            // Check if it's an async task or immediate result
            if (result.task_id) {
                addMessage('bot', `Create: Uploading ${result.filename.join(", ")}... Processing in background.`);
                pollTaskStatus(result.task_id, result.filename);
            } else {
                addMessage('bot', `Create: Processed ${result.filename.join(", ")}`);
                // Clear file input
                document.getElementById('file-upload').value = '';
                // Assuming there's a file-name-display element, if not, this line might cause an error
                // document.getElementById('file-name-display').textContent = '';
            }

        } catch (error) {
            console.error('Error:', error);
            addMessage('bot', `Error: ${error.message}`);
        } finally {
            event.target.value = '';
        }
    }

    async function pollTaskStatus(taskId, filenames) {
        const pollInterval = 2000; // 2 seconds

        const checkStatus = async () => {
            try {
                const response = await fetch(`/api/tasks/${taskId}`);
                const statusData = await response.json();

                if (statusData.status === 'completed') {
                    addMessage('bot', `Create: Successfully processed ${filenames.join(", ")}`);
                    // Clear file input
                    document.getElementById('file-upload').value = '';
                    // document.getElementById('file-name-display').textContent = '';
                } else if (statusData.status === 'failed') {
                    addMessage('bot', `Error: Failed to process files. ${statusData.error}`);
                } else {
                    // Still processing
                    setTimeout(checkStatus, pollInterval);
                }
            } catch (e) {
                console.error("Polling error", e);
                addMessage('bot', `Error: Could not check upload status.`);
            }
        };

        setTimeout(checkStatus, pollInterval);
    }

    // Add message to UI
    function addMessage(sender, text, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message robotic-panel`;
        messageDiv.setAttribute('data-id', Math.random().toString(36).substr(2, 9).toUpperCase());

        const senderDiv = document.createElement('div');
        senderDiv.className = 'message-sender';
        senderDiv.textContent = sender === 'user' ? '// COMMANDER_INPUT' : (sender === 'system' ? '// SYSTEM_LOG' : '// RESILIENCEGPT_RESPONSE');

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';

        messageDiv.appendChild(senderDiv);
        messageDiv.appendChild(textDiv);

        if (timestamp) {
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-time';
            timeDiv.textContent = new Date(timestamp * 1000).toLocaleTimeString();
            messageDiv.appendChild(timeDiv);
        }

        chatOutput.appendChild(messageDiv);
        chatOutput.scrollTop = chatOutput.scrollHeight;

        if (sender === 'bot') {
            typeWriter(textDiv, formatBotResponse(text));
        } else {
            textDiv.innerHTML = formatBotResponse(text);
        }
    }

    // Typewriter effect
    function typeWriter(element, html, speed = 20) {
        let i = 0;
        element.innerHTML = "";
        element.classList.add('typing-cursor');

        // Since it's HTML, we need to handle tags
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        const text = tempDiv.innerText; // Basic version: type text only for now to avoid breaking HTML tags mid-way
        // Rich version: type HTML safely

        let currentText = "";
        const interval = setInterval(() => {
            if (i < html.length) {
                // To properly handle HTML, we should really use a library or a complex regex
                // Simple workaround: show it chunk by chunk or full if it's very complex
                if (html.length > 500) {
                    element.innerHTML = html;
                    clearInterval(interval);
                    element.classList.remove('typing-cursor');
                    return;
                }

                element.innerHTML = html.substring(0, i + 1);
                i++;
                chatOutput.scrollTop = chatOutput.scrollHeight;
            } else {
                clearInterval(interval);
                element.classList.remove('typing-cursor');
            }
        }, 10);
    }

    function showTypingIndicator() {
        if (document.getElementById('typing-indicator')) return; // Already showing

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message robotic-panel';
        messageDiv.id = 'typing-indicator';
        messageDiv.style.borderLeft = '4px solid var(--neon-cyan)'; // Ensure visual consistency

        const senderDiv = document.createElement('div');
        senderDiv.className = 'message-sender';
        senderDiv.textContent = '// SYSTEM_PROCESSING';

        // Advanced Indicator Structure
        const indicatorContainer = document.createElement('div');
        indicatorContainer.className = 'typing-indicator';

        indicatorContainer.innerHTML = `
            <div class="processing-text">
                <span>ANALYZING QUERY</span>
                <span>Wait...</span>
            </div>
            <div class="processing-bar"></div>
            <div class="processing-steps">
                <div class="step-dot"></div>
                <div class="step-dot"></div>
                <div class="step-dot"></div>
            </div>
        `;

        messageDiv.appendChild(senderDiv);
        messageDiv.appendChild(indicatorContainer);
        chatOutput.appendChild(messageDiv);
        chatOutput.scrollTop = chatOutput.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }



    // Format bot response using marked.js
    function formatBotResponse(text) {
        try {
            // Configure marked options if needed
            marked.use({
                breaks: true, // Enable line breaks
                gfm: true     // Enable GitHub Flavored Markdown
            });
            return marked.parse(text);
        } catch (e) {
            console.error("Markdown parsing error:", e);
            return text; // Fallback to raw text
        }
    }

    // Send message to server
    async function sendMessage() {
        window.speechSynthesis.cancel();
        const message = userInput.value.trim();
        if (!currentConversationId) {
            await createNewChat();
        }
        if (message && currentConversationId) {
            addMessage('user', message);
            userInput.value = '';
            userInput.style.height = ''; // Reset height

            // Loading state
            const originalBtnContent = sendButton.innerHTML;
            sendButton.disabled = true;
            sendButton.innerHTML = '<span class="status-pulse" style="display:inline-block; width:10px; height:10px;"></span>';

            const generateImage = document.getElementById("image-gen-checkbox").checked;

            // Show typing indicator
            showTypingIndicator();

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        conversation_id: currentConversationId,
                        mode: currentMode,
                        generate_image: generateImage
                    })
                });

                const data = await response.json();

                // Remove typing indicator before showing result
                removeTypingIndicator();

                if (data.response) {
                    addMessage('bot', data.response);
                }


                if (data.image) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message bot-message';
                    const img = new Image();
                    img.src = 'data:image/png;base64,' + data.image;
                    img.alt = 'Generated Image';
                    img.style.maxWidth = '100%';
                    messageDiv.appendChild(img);
                    chatOutput.appendChild(messageDiv);

                }

                updateChatHistorySidebar();
            } catch (error) {
                console.error('Error:', error);
                removeTypingIndicator();
                addMessage('bot', "Sorry, I encountered an error. Please try again.");
            } finally {
                sendButton.disabled = false;
                sendButton.innerHTML = originalBtnContent;
                // Double safe cleanup
                removeTypingIndicator();
            }
        }
    }

    // Update sidebar with conversation list
    async function updateChatHistorySidebar() {
        try {
            const response = await fetch('/api/conversations');
            const data = await response.json();

            chatHistorySidebar.innerHTML = '';

            const sortedConversations = Object.entries(data.conversations)
                .sort((a, b) => b[1].last_updated - a[1].last_updated);

            for (const [id, conversation] of sortedConversations) {
                const chatItem = document.createElement('div');
                chatItem.className = 'chat-item';
                if (id === currentConversationId) {
                    chatItem.classList.add('active-chat');
                }

                const titleSpan = document.createElement('span');
                titleSpan.className = 'chat-title';
                titleSpan.textContent = conversation.title;

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-chat-btn';
                deleteBtn.innerHTML = '&times;';
                deleteBtn.addEventListener('click', (e) => deleteConversation(id, e));

                chatItem.appendChild(titleSpan);
                chatItem.appendChild(deleteBtn);
                chatItem.addEventListener('click', () => loadConversation(id));

                chatHistorySidebar.appendChild(chatItem);
            }
        } catch (error) {
            console.error('Error fetching conversations:', error);
        }
    }

    // Load a specific conversation
    async function loadConversation(conversationId) {
        window.speechSynthesis.cancel();
        try {
            const response = await fetch(`/api/conversation/${conversationId}`);
            if (!response.ok) throw new Error('Failed to fetch conversation');
            const conversation = await response.json();

            currentConversationId = conversationId;
            currentMode = conversation.mode || 'pakistan';

            chatOutput.innerHTML = '';

            conversation.history.forEach(msg => {
                if (msg.user) addMessage('user', msg.user, msg.timestamp);
                if (msg.bot) addMessage('bot', msg.bot, msg.timestamp);
                if (msg.image) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message bot-message';

                    const img = new Image();
                    img.src = 'data:image/png;base64,' + msg.image;
                    img.alt = 'Generated Image';
                    img.style.maxWidth = '100%';
                    img.style.height = 'auto';

                    messageDiv.appendChild(img);
                    chatOutput.appendChild(messageDiv);
                }
            });

            updateChatHistorySidebar();
        } catch (error) {
            console.error('Error loading conversation:', error);
        }
    }

    // Delete a conversation
    async function deleteConversation(conversationId, event) {
        window.speechSynthesis.cancel();
        event.stopPropagation();

        if (confirm('Are you sure you want to delete this chat?')) {
            try {
                const response = await fetch('/api/delete_chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        conversation_id: conversationId
                    })
                });

                const data = await response.json();
                if (data.status === 'success') {

                    updateChatHistorySidebar();
                }
            } catch (error) {
                console.error('Error deleting conversation:', error);
                alert('Failed to delete chat');
            }
        }
    }

    // Create a new chat
    async function createNewChat() {
        window.speechSynthesis.cancel();
        try {
            const response = await fetch('/api/new_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    mode: currentMode
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                currentConversationId = data.conversation_id;
                chatOutput.innerHTML = '';
                addMessage('bot', 'Hello! How can I assist you today?');
                updateChatHistorySidebar();
            }
        } catch (error) {
            console.error('Error starting new chat:', error);
            alert('Failed to create new chat. Please try again.');
        }
    }

    // Initialize chat on page load
    async function initializeChat() {
        window.speechSynthesis.cancel();
        try {
            const response = await fetch('/api/current_conversation');
            if (response.ok) {
                const data = await response.json();
                currentConversationId = data.conversation_id;
                currentMode = data.conversation.mode || 'pakistan';
                await loadConversation(currentConversationId);
            } else {
                await createNewChat();
            }
        } catch (error) {
            console.error('Error initializing chat:', error);
            await createNewChat();
        }
    }

    // Microphone / audio recording logic
    const audioRecordBtn = document.getElementById("audio-record-btn");
    let mediaRecorder;
    let audioChunks = [];
    let recording = false;

    // Check mic permission and return boolean
    async function checkMicrophonePermission() {
        window.speechSynthesis.cancel();
        try {
            const permissionStatus = await navigator.permissions.query({ name: "microphone" });
            return permissionStatus.state === "granted";
        } catch (err) {
            // If Permissions API not supported, fallback to try getUserMedia
            try {
                await navigator.mediaDevices.getUserMedia({ audio: true });
                return true;
            } catch (e) {
                return false;
            }
        }
    }

    // Start or stop recording on button click
    audioRecordBtn.addEventListener("click", async () => {
        if (recording) {
            stopRecording();
        } else {
            const granted = await checkMicrophonePermission();
            if (!granted) {
                alert("Please enable microphone permission first.");
                return;
            }
            startRecording();
        }
    });

    // Start recording audio
    async function startRecording() {
        window.speechSynthesis.cancel();
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (e) => {
                audioChunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
                audioChunks = [];

                // Convert Blob to File or base64 as needed and send to backend
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64Audio = reader.result.split(",")[1];
                    sendAudioMessage(base64Audio);
                };
                reader.readAsDataURL(audioBlob);
            };

            mediaRecorder.start();
            recording = true;
            audioRecordBtn.classList.add("recording", "neon-border");
            document.querySelector('.status-text').textContent = "LISTENING...";
            console.log("Recording started");
        } catch (err) {
            alert("Could not start recording: " + err.message);
        }
    }

    // Stop recording audio
    function stopRecording() {
        if (mediaRecorder && recording) {
            mediaRecorder.stop();
            recording = false;
            audioRecordBtn.classList.remove("recording", "neon-border");
            document.querySelector('.status-text').textContent = "PROCESSING...";
            console.log("Recording stopped");
        }
    }

    // Send audio data to backend
    async function sendAudioMessage(base64Audio) {
        if (!currentConversationId) {
            await createNewChat();
        }
        try {
            addMessage("user", "[Audio message sent]");
            const generateImage = document.getElementById("image-gen-checkbox").checked;
            const response = await fetch("/chat-audio", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    audio: base64Audio,
                    conversation_id: currentConversationId,
                    mode: currentMode,
                    generate_image: generateImage
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || "Audio chat error");
            }

            currentConversationId = data.conversation_id;

            // Show bot reply text
            addMessage("user", data.user_message);
            addMessage("bot", data.reply);

            if (data.image) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message bot-message';
                const img = new Image();
                img.src = 'data:image/png;base64,' + data.image;
                img.alt = 'Generated Image';
                img.style.maxWidth = '100%';


                // Append image and button
                messageDiv.appendChild(img);
                chatOutput.appendChild(messageDiv);
            }
            // Play audio if returned by backend
            /*
            if (data.audio_base64) {
                const audio = new Audio(data.audio_base64);
                audio.play();
            }*/

            // Optionally speak the text as well
            speakText(data.reply);

        } catch (error) {
            addMessage("system", error.message);
        }
    }


    function speakText(text) {
        if (!("speechSynthesis" in window)) {
            console.warn("Text-to-Speech not supported.");
            return;
        }
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-US'; // adjust if needed
        window.speechSynthesis.speak(utterance);
    }

    async function getAudioStream() {
        try {
            // Get all audio input devices fresh
            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter(device => device.kind === "audioinput");

            // Debug: log device labels & IDs
            console.log("Audio input devices:", audioInputs);

            // Try to find your handsfree device dynamically by label keywords
            let selectedDeviceId = null;
            for (const device of audioInputs) {
                if (device.label.toLowerCase().includes("headset") || device.label.toLowerCase().includes("handsfree")) {
                    selectedDeviceId = device.deviceId;
                    break;
                }
            }

            // If no handsfree device found, use default mic (no deviceId constraint)
            const constraints = selectedDeviceId
                ? { audio: { deviceId: { exact: selectedDeviceId } } }
                : { audio: true };

            // Request the media stream with the constraints
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            return stream;

        } catch (error) {
            console.error("Error getting audio stream:", error);
            throw error;  // or handle gracefully
        }
    }

});
