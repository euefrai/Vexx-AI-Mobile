/**
 * VEXX VOICE MODE (Modo de Voz Conversacional em Tempo Real Estilo ChatGPT Voice)
 * 
 * - Captura contínua de áudio com cancelamento de ruído agressivo
 * - Calibração de locutor e isolamento de voz via SpeechBrain
 * - Transcrição instantânea (Faster-Whisper) e síntese particionada (Kokoro ONNX)
 * - Interrupção instantânea (barge-in) se o usuário falar enquanto a IA fala
 * - Esfera holográfica reativa por Web Audio API AnalyserNode
 */
(function() {
  'use strict';

  // Configurações
  const SAMPLE_RATE = 16000;
  const SILENCE_TIMEOUT_MS = 850;
  const SPEECH_ENERGY_THRESHOLD = 0.025;
  const BARGE_IN_THRESHOLD = 0.045;

  // Elementos do DOM
  let overlay, orb, statusLabel, userSub, aiSub, muteBtn, interruptBtn, closeBtn, voiceSelect, triggerBtn;

  // Estado da Conexão e Áudio
  let ws = null;
  let audioContext = null;
  let micStream = null;
  let micSource = null;
  let analyser = null;
  let mediaRecorder = null;

  let isVoiceModeActive = false;
  let isMuted = false;
  let isCalibrating = true;
  let isAiSpeaking = false;
  let isUserSpeaking = false;
  let currentVoice = 'pm_alex';

  let silenceTimer = null;
  let animFrameId = null;
  let audioPlaybackQueue = [];
  let isPlayingAudio = false;
  let currentAudioSource = null;

  function initElements() {
    overlay = document.getElementById('voiceModeOverlay');
    orb = document.getElementById('voiceOrb');
    statusLabel = document.getElementById('voiceStatusLabel');
    userSub = document.getElementById('voiceUserSubtitle');
    aiSub = document.getElementById('voiceAiSubtitle');
    muteBtn = document.getElementById('voiceMuteBtn');
    interruptBtn = document.getElementById('voiceInterruptBtn');
    closeBtn = document.getElementById('voiceCloseBtn');
    voiceSelect = document.getElementById('voiceSelect');
    triggerBtn = document.getElementById('voiceModeButton');

    if (triggerBtn) {
      triggerBtn.addEventListener('click', toggleVoiceMode);
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', stopVoiceMode);
    }
    if (muteBtn) {
      muteBtn.addEventListener('click', toggleMute);
    }
    if (interruptBtn) {
      interruptBtn.addEventListener('click', handleUserInterrupt);
    }
    if (voiceSelect) {
      voiceSelect.addEventListener('change', (e) => {
        currentVoice = e.target.value;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'init', voice: currentVoice }));
        }
      });
    }
    if (orb) {
      orb.addEventListener('click', () => {
        if (isAiSpeaking) {
          handleUserInterrupt();
        }
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isVoiceModeActive) {
        stopVoiceMode();
      }
    });
  }

  function setVisualState(state, text) {
    if (!orb || !statusLabel) return;
    orb.className = 'voice-orb ' + state;
    if (text) {
      statusLabel.innerHTML = `<span class="voice-status-dot"></span> ${text}`;
    }
    if (state === 'speaking') {
      isAiSpeaking = true;
      if (interruptBtn) interruptBtn.classList.add('visible');
    } else {
      isAiSpeaking = false;
      if (interruptBtn && state !== 'thinking') interruptBtn.classList.remove('visible');
    }
  }

  async function startVoiceMode() {
    if (isVoiceModeActive) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      micStream = stream;
    } catch (err) {
      alert('Permissão de microfone necessária para o Modo de Voz: ' + (err.message || err));
      return;
    }

    isVoiceModeActive = true;
    isCalibrating = true;
    if (triggerBtn) triggerBtn.classList.add('active');
    if (overlay) {
      overlay.hidden = false;
      requestAnimationFrame(() => overlay.classList.add('open'));
    }

    setVisualState('calibrating', 'Reconhecendo sua voz (calibração)...');
    if (userSub) userSub.textContent = '';
    if (aiSub) aiSub.textContent = 'Fale normalmente para sincronizar seu perfil de voz.';

    setupAudioPipeline(micStream);
    connectWebSocket();
  }

  function stopVoiceMode() {
    if (!isVoiceModeActive) return;
    isVoiceModeActive = false;
    handleUserInterrupt();

    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try { mediaRecorder.stop(); } catch (e) {}
    }
    if (micStream) {
      micStream.getTracks().forEach(t => t.stop());
      micStream = null;
    }
    if (audioContext && audioContext.state !== 'closed') {
      audioContext.close();
      audioContext = null;
    }
    if (ws) {
      try { ws.close(); } catch (e) {}
      ws = null;
    }

    if (overlay) {
      overlay.classList.remove('open');
      setTimeout(() => { overlay.hidden = true; }, 350);
    }
    if (triggerBtn) triggerBtn.classList.remove('active');
    setVisualState('idle', 'Toque no microfone para conversar');
  }

  function toggleVoiceMode() {
    if (isVoiceModeActive) {
      stopVoiceMode();
    } else {
      startVoiceMode();
    }
  }

  function toggleMute() {
    isMuted = !isMuted;
    if (micStream) {
      micStream.getAudioTracks().forEach(t => t.enabled = !isMuted);
    }
    if (muteBtn) {
      muteBtn.classList.toggle('muted', isMuted);
      muteBtn.title = isMuted ? 'Desmutar Microfone' : 'Mutar Microfone';
    }
    setVisualState(isMuted ? 'idle' : 'listening', isMuted ? 'Microfone mutado' : 'Ouvindo você...');
  }

  function setupAudioPipeline(stream) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioCtx({ sampleRate: SAMPLE_RATE });
    micSource = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.4;
    micSource.connect(analyser);

    startVisualizerLoop();
    startMediaRecorder(stream);
  }

  function startVisualizerLoop() {
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    function renderFrame() {
      if (!isVoiceModeActive || !analyser) return;
      animFrameId = requestAnimationFrame(renderFrame);

      analyser.getByteTimeDomainData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const val = (dataArray[i] - 128) / 128;
        sum += val * val;
      }
      const energy = Math.sqrt(sum / dataArray.length);

      // Reage o Orb dinamicamente
      if (orb && !isAiSpeaking) {
        const scale = 1.0 + Math.min(energy * 2.2, 0.45);
        orb.style.transform = `scale(${scale})`;
      }

      // Detecção de Fala / Silêncio
      if (!isMuted) {
        // BARGE-IN: Se a IA estiver falando e o usuário começar a falar
        if (isAiSpeaking && energy > BARGE_IN_THRESHOLD) {
          handleUserInterrupt();
          return;
        }

        if (energy > SPEECH_ENERGY_THRESHOLD) {
          if (!isUserSpeaking && !isAiSpeaking) {
            isUserSpeaking = true;
            setVisualState('listening', 'Ouvindo você...');
          }
          if (silenceTimer) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
          }
        } else if (isUserSpeaking) {
          if (!silenceTimer) {
            silenceTimer = setTimeout(() => {
              isUserSpeaking = false;
              silenceTimer = null;
              if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'audio_end' }));
                setVisualState('thinking', 'Processando fala...');
              }
            }, SILENCE_TIMEOUT_MS);
          }
        }
      }
    }
    renderFrame();
  }

  function startMediaRecorder(stream) {
    let mimeType = 'audio/webm';
    if (!MediaRecorder.isTypeSupported('audio/webm')) {
      mimeType = MediaRecorder.isTypeSupported('audio/ogg;codecs=opus') ? 'audio/ogg;codecs=opus' : '';
    }

    const options = mimeType ? { mimeType } : {};
    try {
      mediaRecorder = new MediaRecorder(stream, options);
    } catch (e) {
      mediaRecorder = new MediaRecorder(stream);
    }

    mediaRecorder.ondataavailable = async (event) => {
      if (event.data && event.data.size > 0 && ws && ws.readyState === WebSocket.OPEN && !isMuted) {
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64Data = reader.result.split(',')[1];
          if (isCalibrating) {
            ws.send(JSON.stringify({ type: 'calibrate', audio: base64Data }));
            isCalibrating = false;
            setVisualState('listening', 'Voz calibrada! Pode falar...');
          } else {
            ws.send(JSON.stringify({ type: 'audio_chunk', data: base64Data }));
          }
        };
        reader.readAsDataURL(event.data);
      }
    };

    // Fatias curtas de 250ms para streaming contínuo ultra-responsivo
    mediaRecorder.start(250);
  }

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/voice-chat-stream`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      ws.send(JSON.stringify({
        type: 'init',
        voice: currentVoice,
        speed: 1.0,
        model: ''
      }));
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } catch (e) {
        console.error('Erro ao processar mensagem do WebSocket de Voz:', e);
      }
    };

    ws.onerror = (err) => {
      console.warn('WebSocket de Voz erro:', err);
      setVisualState('idle', 'Falha de conexão com a API de Voz.');
    };

    ws.onclose = () => {
      if (isVoiceModeActive) {
        setVisualState('idle', 'Conexão encerrada.');
      }
    };
  }

  function handleServerMessage(msg) {
    const type = msg.type;

    if (type === 'voice_ready') {
      if (!isCalibrating) {
        setVisualState('listening', 'Ouvindo você...');
      }
    } else if (type === 'calibrated') {
      isCalibrating = false;
      setVisualState('listening', 'Perfil de voz configurado. Pode conversar!');
      if (aiSub) aiSub.textContent = 'Estou te ouvindo. Diga algo!';
    } else if (type === 'user_transcription') {
      if (userSub) userSub.textContent = `Você: "${msg.text}"`;
      setVisualState('thinking', 'Pensando na resposta...');
      if (aiSub) aiSub.textContent = '...';
    } else if (type === 'voice_filtered') {
      if (statusLabel) {
        statusLabel.textContent = 'Voz de fundo ignorada (filtro anti-intrusos ativo).';
      }
      setTimeout(() => {
        if (!isAiSpeaking && isVoiceModeActive) {
          setVisualState('listening', 'Ouvindo você...');
        }
      }, 1500);
    } else if (type === 'ai_text_delta') {
      if (aiSub) {
        if (aiSub.textContent === '...') aiSub.textContent = '';
        aiSub.textContent += msg.delta;
      }
    } else if (type === 'ai_audio_delta') {
      // Chunk de áudio gerado pelo Kokoro
      enqueueAudioChunk(msg.audio, msg.text);
    } else if (type === 'ai_done') {
      if (aiSub && msg.response_text) {
        aiSub.textContent = msg.response_text;
      }
    } else if (type === 'interrupted' || type === 'cancelled') {
      handleUserInterrupt();
    } else if (type === 'error') {
      if (statusLabel) statusLabel.textContent = msg.message || 'Erro no assistente';
      setTimeout(() => {
        if (isVoiceModeActive) setVisualState('listening', 'Ouvindo você...');
      }, 2000);
    }
  }

  function handleUserInterrupt() {
    // Interrompe reprodução atual do assistente
    if (currentAudioSource) {
      try { currentAudioSource.stop(); } catch (e) {}
      currentAudioSource = null;
    }
    audioPlaybackQueue = [];
    isPlayingAudio = false;
    isAiSpeaking = false;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }));
    }
    setVisualState('listening', 'Ouvindo você...');
  }

  function enqueueAudioChunk(base64Wav, text) {
    audioPlaybackQueue.push({ base64Wav, text });
    if (!isPlayingAudio) {
      playNextAudioChunk();
    }
  }

  async function playNextAudioChunk() {
    if (audioPlaybackQueue.length === 0) {
      isPlayingAudio = false;
      if (isVoiceModeActive && !isUserSpeaking) {
        setVisualState('listening', 'Ouvindo você...');
      }
      return;
    }

    isPlayingAudio = true;
    setVisualState('speaking', 'Vexx falando...');
    const item = audioPlaybackQueue.shift();

    try {
      const raw = atob(item.base64Wav);
      const arrayBuffer = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) {
        arrayBuffer[i] = raw.charCodeAt(i);
      }

      if (!audioContext || audioContext.state === 'closed') {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        audioContext = new AudioCtx({ sampleRate: SAMPLE_RATE });
      }

      const decodedBuffer = await audioContext.decodeAudioData(arrayBuffer.buffer);
      const source = audioContext.createBufferSource();
      source.buffer = decodedBuffer;
      source.connect(audioContext.destination);
      currentAudioSource = source;

      source.onended = () => {
        currentAudioSource = null;
        playNextAudioChunk();
      };
      source.start(0);
    } catch (err) {
      console.warn('Erro na reprodução de chunk de áudio Kokoro:', err);
      playNextAudioChunk();
    }
  }

  // Inicialização no DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initElements);
  } else {
    initElements();
  }

  // Exporta objeto global para uso programático
  window.VexxVoice = {
    start: startVoiceMode,
    stop: stopVoiceMode,
    toggle: toggleVoiceMode,
    interrupt: handleUserInterrupt,
    isActive: () => isVoiceModeActive
  };
})();
