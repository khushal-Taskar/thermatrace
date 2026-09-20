"use client";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {AnimatePresence,motion} from "framer-motion";
import {Bot,BrainCircuit,CheckCircle2,Clock3,Database,Headphones,History,Languages,Mic,MicOff,PhoneCall,PhoneOff,Radio,Send,ShieldCheck,Sparkles,TriangleAlert,Volume2} from "lucide-react";
import {useMonitor} from "@/hooks/use-monitor";
import {api,apiForm} from "@/lib/api";
import {cn,time} from "@/lib/utils";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Badge} from "@/components/status";
import type {VoiceRuntime,VoiceSession,VoiceTurn} from "@/types";

const voiceLanguages=[
 {value:"auto",label:"Auto-detect"},{value:"hi",label:"Hindi"},{value:"en",label:"English"},{value:"mr",label:"Marathi"},
];
const languageLabel=(value:string)=>voiceLanguages.find(item=>item.value===value)?.label||value.toUpperCase();

type BrowserSpeechRecognition={
 lang:string;continuous:boolean;interimResults:boolean;maxAlternatives:number;
 onstart:(event:Event)=>void;onresult:(event:{resultIndex:number;results:ArrayLike<{isFinal:boolean;0:{transcript:string}}>} )=>void;
 onerror:(event:{error?:string})=>void;onend:(event:Event)=>void;start:()=>void;stop:()=>void;abort:()=>void;
};
type BrowserSpeechRecognitionConstructor=new()=>BrowserSpeechRecognition;

function browserSpeechConstructor(){
 if(typeof window==="undefined")return null;
 const voiceWindow=window as typeof window&{SpeechRecognition?:BrowserSpeechRecognitionConstructor;webkitSpeechRecognition?:BrowserSpeechRecognitionConstructor};
 return voiceWindow.SpeechRecognition||voiceWindow.webkitSpeechRecognition||null;
}

function elapsed(from:string){const normalized=from.endsWith("Z")||/[+-]\d\d:\d\d$/.test(from)?from:`${from}Z`;const seconds=Math.max(0,Math.floor((Date.now()-new Date(normalized).getTime())/1000));return `${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`;}

export function VoiceCenter(){
 const {data,user,notify}=useMonitor();
 const [runtime,setRuntime]=useState<VoiceRuntime|null>(null),[history,setHistory]=useState<VoiceSession[]>([]),[session,setSession]=useState<VoiceSession|null>(null);
 const [vehicleId,setVehicleId]=useState(data?.fleet[0]?.vehicle.vehicle_id||""),[language,setLanguage]=useState("auto"),[recording,setRecording]=useState(false),[speaking,setSpeaking]=useState(false),[busy,setBusy]=useState(false),[voiceFeedback,setVoiceFeedback]=useState<string|null>(null),[draft,setDraft]=useState(""),[clock,setClock]=useState("00:00"),[detail,setDetail]=useState<VoiceSession|null>(null),[browserSpeechAvailable,setBrowserSpeechAvailable]=useState(false);
 const recorder=useRef<MediaRecorder|null>(null),speechRecognition=useRef<BrowserSpeechRecognition|null>(null),chunks=useRef<Blob[]>([]),stream=useRef<MediaStream|null>(null),activeAudio=useRef<HTMLAudioElement|null>(null),messagesEnd=useRef<HTMLDivElement|null>(null),audioReplies=useRef(new Map<number,{base64:string,mime:string,language:string}>());
 const canCall=user?.role==="ADMIN"||user?.role==="OPERATOR";
 const microphoneAvailable=Boolean(runtime?.speech_to_text||browserSpeechAvailable);
 const selected=useMemo(()=>data?.fleet.find(item=>item.vehicle.vehicle_id===(session?.vehicle_id||vehicleId)),[data,vehicleId,session?.vehicle_id]);
 const load=useCallback(async()=>{try{const [status,calls]=await Promise.all([api<VoiceRuntime>("/voice/status"),api<VoiceSession[]>("/voice/sessions")]);setRuntime(status);setHistory(calls);}catch(e){notify((e as Error).message);}},[notify]);
 useEffect(()=>{load();},[load]);
 useEffect(()=>{setBrowserSpeechAvailable(Boolean(browserSpeechConstructor()));},[]);
 useEffect(()=>{if(!session||session.status!=="ACTIVE")return;const timer=setInterval(()=>setClock(elapsed(session.started_at)),1000);return()=>clearInterval(timer);},[session]);
 useEffect(()=>{messagesEnd.current?.scrollIntoView({behavior:"smooth"});},[session?.messages?.length]);
 useEffect(()=>()=>{speechRecognition.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());activeAudio.current?.pause();window.speechSynthesis?.cancel();},[]);

 function playAnswer(messageId:number,text:string,language:string){
   activeAudio.current?.pause();window.speechSynthesis?.cancel();setSpeaking(true);setVoiceFeedback("Speaking the local AI answer…");
   const reply=audioReplies.current.get(messageId);
   if(!reply){browserSpeak(text,language);return;}
   const binary=atob(reply.base64),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
   const url=URL.createObjectURL(new Blob([bytes],{type:reply.mime})),audio=new Audio(url);
   activeAudio.current=audio;
   audio.onended=()=>{URL.revokeObjectURL(url);activeAudio.current=null;setSpeaking(false);setVoiceFeedback(null);};audio.onerror=()=>{URL.revokeObjectURL(url);activeAudio.current=null;browserSpeak(text,reply.language);};
   audio.play().catch(()=>{URL.revokeObjectURL(url);activeAudio.current=null;browserSpeak(text,reply.language);});
 }
 function browserSpeak(text:string,lang:string){if(!window.speechSynthesis){setSpeaking(false);setVoiceFeedback("The answer is ready in the transcript. Press Play answer to hear it.");return;}window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(text);const locales:Record<string,string>={hi:"hi-IN",en:"en-IN",mr:"mr-IN"};utterance.lang=locales[lang]||lang;utterance.rate=.96;utterance.onend=()=>{setSpeaking(false);setVoiceFeedback(null);};utterance.onerror=()=>{setSpeaking(false);setVoiceFeedback("The answer is ready in the transcript. Press Play answer to retry audio.");};window.speechSynthesis.speak(utterance);}
 async function startCall(){setBusy(true);try{const next=await api<VoiceSession>("/voice/sessions",{method:"POST",body:JSON.stringify({vehicle_id:vehicleId||null,language})});setSession(next);setDetail(null);setClock("00:00");notify("Local AI voice session started");}catch(e){notify((e as Error).message);}finally{setBusy(false);}}
 async function finishCall(){if(!session)return;if(recording)stopRecording();setBusy(true);try{const completed=await api<VoiceSession>(`/voice/sessions/${session.id}/end`,{method:"POST"});setSession(completed);setDetail(completed);await load();notify("Call ended and structured notes were saved");}catch(e){notify((e as Error).message);}finally{setBusy(false);}}
 function appendTurn(turn:VoiceTurn){if(turn.audio_base64)audioReplies.current.set(turn.assistant.id,{base64:turn.audio_base64,mime:turn.audio_mime||"audio/wav",language:turn.spoken_language});setSession(current=>current?{...current,vehicle_id:turn.vehicle_id,messages:[...(current.messages||[]),turn.operator,turn.assistant]}:current);setVoiceFeedback("Answer ready. Playing it now…");window.setTimeout(()=>playAnswer(turn.assistant.id,turn.assistant.text,turn.spoken_language),80);}
 async function submitQuestion(question:string){if(!session||!question.trim()||busy)return;setBusy(true);try{const turn=await api<VoiceTurn>(`/voice/sessions/${session.id}/message`,{method:"POST",body:JSON.stringify({text:question.trim(),language})});appendTurn(turn);}catch(e){notify((e as Error).message);}finally{setBusy(false);}}
 async function sendText(){const question=draft.trim();if(!question)return;setDraft("");await submitQuestion(question);}
 async function upload(blob:Blob){if(!session)return;setBusy(true);setVoiceFeedback("Transcribing speech and checking live telemetry…");try{const form=new FormData();form.append("audio",blob,`turn.${blob.type.includes("mp4")?"mp4":"webm"}`);form.append("language",language);const turn=await apiForm<VoiceTurn>(`/voice/sessions/${session.id}/turn`,form);appendTurn(turn);}catch(e){const message=(e as Error).message;setVoiceFeedback(message);notify(message);}finally{setBusy(false);}}
 async function startRecording(){
   if(!session||busy)return;
   try{
     activeAudio.current?.pause();window.speechSynthesis?.cancel();setSpeaking(false);setVoiceFeedback(null);
     if(!runtime?.speech_to_text){
       const SpeechRecognition=browserSpeechConstructor();
       if(!SpeechRecognition)throw new Error("This browser does not provide speech recognition. Use Chrome or Edge, or type your question below.");
       const recognition=new SpeechRecognition(),locales:Record<string,string>={hi:"hi-IN",en:"en-IN",mr:"mr-IN"};
       let finalText="",recognitionFailed=false;
       recognition.lang=locales[language]||navigator.language||"en-IN";recognition.continuous=false;recognition.interimResults=true;recognition.maxAlternatives=1;
       recognition.onstart=()=>{setRecording(true);setVoiceFeedback("Listening through the browser microphone…");};
       recognition.onresult=event=>{let heard="";for(let i=event.resultIndex;i<event.results.length;i++){const text=event.results[i][0]?.transcript||"";heard+=text;if(event.results[i].isFinal)finalText+=text;}if(heard.trim())setVoiceFeedback(`Heard: ${heard.trim()}`);};
       recognition.onerror=event=>{recognitionFailed=true;const denied=event.error==="not-allowed"||event.error==="service-not-allowed";const message=denied?"Microphone permission was denied. Allow microphone access, or type your question below.":"Browser speech recognition could not hear a complete question. Please try again.";setRecording(false);setVoiceFeedback(message);notify(message);};
       recognition.onend=()=>{speechRecognition.current=null;setRecording(false);const question=finalText.trim();if(question){setVoiceFeedback("Checking live telemetry…");void submitQuestion(question);}else if(!recognitionFailed){setVoiceFeedback("No speech was detected. Press the microphone and try again.");}};
       speechRecognition.current=recognition;recognition.start();return;
     }
     if(!navigator.mediaDevices?.getUserMedia)throw new Error("Microphone access requires localhost or HTTPS in Chrome/Edge");
     stream.current=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
     const preferred=["audio/webm;codecs=opus","audio/webm","audio/mp4"].find(type=>MediaRecorder.isTypeSupported(type));
     recorder.current=new MediaRecorder(stream.current,preferred?{mimeType:preferred}:undefined);chunks.current=[];
     recorder.current.ondataavailable=event=>{if(event.data.size)chunks.current.push(event.data);};
     recorder.current.onerror=()=>{const message="The browser could not record microphone audio. Check microphone permission and try again.";setRecording(false);setVoiceFeedback(message);notify(message);};
     recorder.current.onstop=()=>{const type=recorder.current?.mimeType||"audio/webm";const blob=new Blob(chunks.current,{type});stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;if(blob.size>200){void upload(blob);}else{const message="No microphone audio was captured. Check the selected input device and speak for at least one second.";setVoiceFeedback(message);notify(message);}};
     recorder.current.start(250);setRecording(true);
   }catch(e){const message=(e as Error).message;setVoiceFeedback(message);notify(message);}
 }
 function stopRecording(){if(speechRecognition.current){setVoiceFeedback("Preparing your question…");speechRecognition.current.stop();return;}if(recorder.current?.state==="recording"){setVoiceFeedback("Preparing the recording…");recorder.current.stop();}setRecording(false);}
 async function openHistory(id:number){setBusy(true);try{setDetail(await api<VoiceSession>(`/voice/sessions/${id}`));}catch(e){notify((e as Error).message);}finally{setBusy(false);}}

 return <div className="voice-page">
   <div className="voice-runtime-strip">
    <span className={cn("runtime-dot",(runtime?.ready||browserSpeechAvailable)&&"ready")}/><strong>{runtime?.ready?"Local voice intelligence ready":browserSpeechAvailable?"Browser voice fallback ready":"Voice runtime unavailable"}</strong>
    <span><BrainCircuit size={13}/>{runtime?.ollama_model||"Qwen local model"}</span><span><Mic size={13}/>{runtime?.speech_to_text?(runtime.whisper_model||"Whisper"):browserSpeechAvailable?"Browser speech recognition":"Typed questions"}</span><span><ShieldCheck size={13}/>Audio is not stored by ThermaTrace</span>
   </div>
   <div className="voice-layout">
    <Card className="voice-call-card">
      {!session||session.status!=="ACTIVE"?<div className="voice-start-state">
        <div className="voice-agent-mark"><div><Bot size={42}/><span/></div></div>
        <span className="eyebrow">THERMATRACE VOICE OPERATIONS</span><h2>Call the AI driver agent</h2><p>Select a vehicle, then ask about battery margin, container safety, route conditions, alerts, or destination reachability.</p>
        <div className="voice-config"><label>Vehicle context<select value={vehicleId} onChange={event=>setVehicleId(event.target.value)}>{data?.fleet.map(item=><option key={item.vehicle.vehicle_id} value={item.vehicle.vehicle_id}>{item.vehicle.vehicle_id} · {item.vehicle.vehicle_name}</option>)}</select></label><label>Conversation language<select value={language} onChange={event=>setLanguage(event.target.value)}>{voiceLanguages.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
        {canCall?<Button onClick={startCall} disabled={busy||!vehicleId}><PhoneCall size={17}/>{busy?"Starting local agent…":"Start secure voice call"}</Button>:<div className="info-callout"><ShieldCheck size={18}/><p>Viewer accounts can review completed call notes. Admin or Operator access is required to start a conversation.</p></div>}
        <small><Database size={12}/> Answers are grounded in live SQL telemetry and timestamped operational records.</small>
      </div>:<div className="voice-active-state">
        <header><div><span className="eyebrow">ACTIVE LOCAL SESSION</span><h2>{session.vehicle_id||"Fleet operations"}</h2></div><div className="call-clock"><span/><Clock3 size={14}/>{clock}</div></header>
        <div className={cn("voice-orb",recording&&"listening",busy&&!recording&&"thinking")}><div><Headphones size={38}/></div>{[0,1,2,3,4,5,6].map(i=><i key={i}/>)}</div>
        <strong className="voice-state-label">{recording?"Listening…":speaking?"Speaking…":busy?"Checking live telemetry…":"AI driver agent connected"}</strong><p className="voice-instruction">{recording?"Speak naturally, then press the microphone again.":voiceFeedback||"Press the microphone and ask your next question."}</p>
        <div className="call-actions"><Button variant="outline" className="end-call" onClick={finishCall} disabled={busy||recording}><PhoneOff size={17}/>End call</Button><button className={cn("mic-control",recording&&"active")} aria-label={recording?"Stop recording":"Start recording"} onClick={recording?stopRecording:startRecording} disabled={busy||!microphoneAvailable} title={microphoneAvailable?"Talk to the AI operations agent":"Use Chrome or Edge for microphone questions"}>{recording?<MicOff size={27}/>:<Mic size={27}/>}</button><span className="language-pill"><Languages size={14}/>{languageLabel(language)}</span></div>
        <div className="voice-transcript" aria-live="polite">{!session.messages?.length&&<div className="voice-empty"><Sparkles size={18}/><p>Try “Kya yeh vehicle destination tak safely pahunch jayegi?”</p></div>}<AnimatePresence>{session.messages?.map(message=><motion.div initial={{opacity:0,y:5}} animate={{opacity:1,y:0}} key={message.id} className={cn("voice-message",message.role.toLowerCase())}><span>{message.role==="USER"?"YOU":"AI AGENT"} · {time(message.created_at)}</span><p>{message.text}</p>{message.role==="ASSISTANT"&&<button onClick={()=>playAnswer(message.id,message.text,message.language)} aria-label="Play answer"><Volume2 size={14}/>Play answer</button>}</motion.div>)}</AnimatePresence><div ref={messagesEnd}/></div>
        <div className="voice-text-fallback"><input value={draft} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==="Enter")sendText();}} placeholder="Type a question when a microphone is unavailable…"/><Button size="icon" onClick={sendText} disabled={busy||!draft.trim()} aria-label="Send typed question"><Send size={16}/></Button></div>
      </div>}
    </Card>
    <div className="voice-side-column">
      <Card className="voice-context-card"><div className="card-heading"><div><span className="eyebrow">LIVE CALL CONTEXT</span><h2>{selected?.vehicle.vehicle_id||"Select a vehicle"}</h2></div><Radio size={18}/></div>{selected?<><div className="context-risk"><div><span>AI risk score</span><strong>{selected.risk.risk_score}<small>/100</small></strong></div><Badge value={selected.risk.risk_level}/></div><div className="context-grid"><div><span>Battery SOC</span><strong>{selected.battery.soc.toFixed(1)}%</strong></div><div><span>Battery temp</span><strong>{selected.battery.battery_temperature.toFixed(1)}°C</strong></div><div><span>Container</span><strong>{selected.container.temperature.toFixed(1)}°C</strong></div><div><span>Distance left</span><strong>{selected.delivery.distance_remaining.toFixed(1)} km</strong></div></div><div className="voice-recommendation"><TriangleAlert size={16}/><p>{selected.risk.recommended_action}</p></div></>:<div className="empty">Vehicle context will appear here.</div>}</Card>
      <Card className="voice-privacy-card"><ShieldCheck size={20}/><div><strong>Privacy-aware voice</strong><p>{runtime?.speech_to_text?"Speech recognition runs on the configured ThermaTrace server; raw recordings are deleted after transcription.":"On this deployment, the browser converts speech to text. ThermaTrace stores the transcript and call note, but does not store microphone audio."}</p></div></Card>
    </div>
   </div>
   <div className="voice-history-heading"><div><span className="eyebrow">CONVERSATION RECORDS</span><h2>Call notes & history</h2></div><span>{history.length} saved sessions</span></div>
   <div className="voice-history-layout"><div className="voice-history-list">{history.length?history.map(item=><button key={item.id} className={cn("voice-history-row",detail?.id===item.id&&"selected")} onClick={()=>openHistory(item.id)}><div className="history-icon"><History size={17}/></div><div><strong>{item.vehicle_id||"Fleet consultation"}</strong><p>{item.summary||"Conversation in progress"}</p><span>{new Date(item.started_at).toLocaleString()} · {item.language.toUpperCase()}</span></div><span className={cn("call-status",item.status.toLowerCase())}>{item.status}</span></button>):<div className="empty">Completed calls and their structured notes will appear here.</div>}</div>
    <Card className="voice-notes-card">{detail?<><div className="card-heading"><div><span className="eyebrow">AI-GENERATED CALL NOTE</span><h2>{detail.vehicle_id||"Fleet consultation"}</h2></div><CheckCircle2 size={20}/></div><p className="note-summary">{detail.summary||"End the active call to generate its final note."}</p><NoteGroup title="Topics" values={detail.notes.topics}/><NoteGroup title="Key telemetry at close" values={detail.notes.key_facts}/><NoteGroup title="Risks discussed" values={detail.notes.risks} warning/><NoteGroup title="Recommended follow-up" values={detail.notes.recommended_actions}/>{detail.messages&&<details><summary>View complete transcript</summary><div className="note-transcript">{detail.messages.map(message=><p key={message.id}><strong>{message.role==="USER"?"Operator":"AI Agent"}</strong>{message.text}</p>)}</div></details>}</>:<div className="voice-note-empty"><Database size={25}/><h3>Select a call record</h3><p>The closing summary, risks, telemetry facts, recommended actions, and complete transcript will appear here.</p></div>}</Card>
   </div>
 </div>;
}

function NoteGroup({title,values,warning=false}:{title:string;values?:string[];warning?:boolean}){if(!values?.length)return null;return <div className={cn("note-group",warning&&"warning")}><span>{title}</span>{values.map((value,index)=><p key={`${value}-${index}`}><i/>{value}</p>)}</div>;}
