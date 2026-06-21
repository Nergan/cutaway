let pc = null;
let ws = null;

window.startWebRTC = (clientId, wsUrl) => {
    ws = new WebSocket(wsUrl);
    
    ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        
        if (msg.type === 'offer') {
            pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
            
            pc.onicecandidate = (e) => {
                if (e.candidate) ws.send(JSON.stringify({ type: 'candidate', candidate: e.candidate }));
            };

            // Use desktopCapture to get the entire Xvfb screen seamlessly (bypasses gesture block)
            chrome.desktopCapture.chooseDesktopMedia(['screen', 'audio'], (streamId) => {
                if (!streamId) {
                    ws.send(JSON.stringify({ type: 'error', message: 'Capture rejected or failed.' }));
                    return;
                }
                
                navigator.mediaDevices.getUserMedia({
                    audio: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: streamId } },
                    video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: streamId, maxWidth: 1920, maxHeight: 1080 } }
                }).then(async (stream) => {
                    stream.getTracks().forEach(track => pc.addTrack(track, stream));

                    await pc.setRemoteDescription(new RTCSessionDescription(msg.offer));
                    const answer = await pc.createAnswer();
                    await pc.setLocalDescription(answer);
                    ws.send(JSON.stringify({ type: 'answer', answer: answer }));
                }).catch(err => {
                    ws.send(JSON.stringify({ type: 'error', message: 'Stream hook error: ' + err.message }));
                });
            });
        } else if (msg.type === 'candidate' && pc) {
            try { await pc.addIceCandidate(new RTCIceCandidate(msg.candidate)); } catch(e) {}
        }
    };
};