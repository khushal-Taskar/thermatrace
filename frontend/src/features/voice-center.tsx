"use client";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {AnimatePresence,motion} from "framer-motion";
import Link from "next/link";
import {Bot,BrainCircuit,CheckCircle2,Clock3,Database,Headphones,History,Languages,Mic,MicOff,PhoneCall,PhoneOff,Radio,Send,ShieldCheck,Sparkles,TriangleAlert,Truck,Volume2} from "lucide-react";
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
const suggestedQuestions=["बैटरी की रेंज कितनी है?","कंटेनर में कौन सी दवा है?","Risk high क्यों है?","Active alerts बताओ","ETA और route deviation बताओ","Rescue request Dispatch को भेजो"];

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

const speechLocales:Record<string,string>={hi:"hi-IN",en:"en-IN",mr:"mr-IN"};

function selectSpeechVoice(voices:SpeechSynthesisVoice[],language:string){
 const code=language.split("-")[0].toLowerCase(),locale=(speechLocales[code]||language).toLowerCase();
 const exact=voices.filter(voice=>voice.lang.toLowerCase()===locale);
 const sameLanguage=voices.filter(voice=>voice.lang.toLowerCase().split("-")[0]===code);
 const named=voices.filter(voice=>voice.name.toLowerCase().includes(code==="mr"?"marathi":code==="hi"?"hindi":"english"));
 const hindiFallback=code==="mr"?voices.filter(voice=>voice.lang.toLowerCase().startsWith("hi")||voice.name.toLowerCase().includes("hindi")):[];
 return exact[0]||sameLanguage[0]||named[0]||hindiFallback[0]||null;
}

function speechText(text:string,language:string){
 if(language.split("-")[0]!=="mr")return text;
 const digitNames:Record<string,string>={"0":"शून्य","1":"एक","2":"दोन","3":"तीन","4":"चार","5":"पाच","6":"सहा","7":"सात","8":"आठ","9":"नऊ"};
 return text
  .replace(/PHARMA-EV-(\d{3})/gi,(_,digits:string)=>`फार्मा ई व्ही ${[...digits].map(digit=>digitNames[digit]).join(" ")}`)
  .replace(/\bSOC\b/gi,"चार्ज पातळी")
  .replace(/°\s*C\b/gi," अंश सेल्सियस")
  .replace(/(\d+(?:\.\d+)?)\s*%/g,"$1 टक्के")
  .replace(/(\d+(?:\.\d+)?)\s*\/\s*100/g,"शंभर पैकी $1")
  .replace(/\bkm\b/gi,"किलोमीटर")
  .replace(/Stop safely, reduce load, and inspect the battery cooling system\.?/gi,"वाहन सुरक्षितपणे थांबवा, भार कमी करा आणि बॅटरीची शीतकरण यंत्रणा तपासा.");
}

function speechChunks(text:string,maxLength=190){
 const sentences=text.match(/[^.!?।]+[.!?।]?/g)?.map(part=>part.trim()).filter(Boolean)||[text];
 const chunks:string[]=[];
 for(const sentence of sentences){
  if(!chunks.length||chunks[chunks.length-1].length+sentence.length+1>maxLength)chunks.push(sentence);
  else chunks[chunks.length-1]+=` ${sentence}`;
 }
 return chunks;
}

async function availableSpeechVoices(synth:SpeechSynthesis){
 const current=synth.getVoices();
 if(current.length)return current;
 return await new Promise<SpeechSynthesisVoice[]>(resolve=>{
  let settled=false;
  const finish=()=>{if(settled)return;settled=true;synth.removeEventListener("voiceschanged",finish);resolve(synth.getVoices());};
  synth.addEventListener("voiceschanged",finish,{once:true});window.setTimeout(finish,1200);
 });
}

function elapsed(from:string){const normalized=from.endsWith("Z")||/[+-]\d\d:\d\d$/.test(from)?from:`${from}Z`;const seconds=Math.max(0,Math.floor((Date.now()-new Date(normalized).getTime())/1000));return `${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`;}

export function VoiceCenter(){
 const {data,user,refresh,notify}=useMonitor();
 const [runtime,setRuntime]=useState<VoiceRuntime|null>(null),[history,setHistory]=useState<VoiceSession[]>([]),[session,setSession]=useState<VoiceSession|null>(null);
 const [vehicleId,setVehicleId]=useState(data?.fleet[0]?.vehicle.vehicle_id||""),[language,setLanguage]=useState("auto"),[speechMode,setSpeechMode]=useState<"browser"|"local">("browser"),[recording,setRecording]=useState(false),[speaking,setSpeaking]=useState(false),[busy,setBusy]=useState(false),[handsFree,setHandsFree]=useState(true),[voiceFeedback,setVoiceFeedback]=useState<string|null>(null),[draft,setDraft]=useState(""),[clock,setClock]=useState("00:00"),[detail,setDetail]=useState<VoiceSession|null>(null),[browserSpeechAvailable,setBrowserSpeechAvailable]=useState(false);
 const [lastRescue,setLastRescue]=useState<VoiceTurn["rescue_mission"]>(null);
 const recorder=useRef<MediaRecorder|null>(null),speechRecognition=useRef<BrowserSpeechRecognition|null>(null),chunks=useRef<Blob[]>([]),stream=useRef<MediaStream|null>(null),activeAudio=useRef<HTMLAudioElement|null>(null),messagesEnd=useRef<HTMLDivElement|null>(null),audioReplies=useRef(new Map<number,{base64:string,mime:string,language:string}>()),speechRun=useRef(0),handsFreeRef=useRef(true),activeSessionRef=useRef(false),startRecordingRef=useRef<()=>Promise<void>>(async()=>{});
 const canCall=user?.role==="ADMIN"||user?.role==="OPERATOR";
 const microphoneAvailable=Boolean(runtime?.speech_to_text||browserSpeechAvailable);
 const selected=useMemo(()=>data?.fleet.find(item=>item.vehicle.vehicle_id===(session?.vehicle_id||vehicleId)),[data,vehicleId,session?.vehicle_id]);
 const load=useCallback(async()=>{try{const [status,calls]=await Promise.all([api<VoiceRuntime>("/voice/status"),api<VoiceSession[]>("/voice/sessions")]);setRuntime(status);setHistory(calls);}catch(e){notify((e as Error).message);}},[notify]);
 useEffect(()=>{load();},[load]);
 useEffect(()=>{setBrowserSpeechAvailable(Boolean(browserSpeechConstructor()));},[]);
 useEffect(()=>{if(!session||session.status!=="ACTIVE")return;const timer=setInterval(()=>setClock(elapsed(session.started_at)),1000);return()=>clearInterval(timer);},[session]);
 useEffect(()=>{messagesEnd.current?.scrollIntoView({behavior:"smooth"});},[session?.messages?.length]);
 useEffect(()=>{handsFreeRef.current=handsFree;activeSessionRef.current=session?.status==="ACTIVE";},[handsFree,session]);
 useEffect(()=>()=>{speechRun.current+=1;speechRecognition.current?.abort();stream.current?.getTracks().forEach(track=>track.stop());activeAudio.current?.pause();window.speechSynthesis?.cancel();},[]);

 function resumeListening(){if(!handsFreeRef.current||!activeSessionRef.current)return;window.setTimeout(()=>{if(handsFreeRef.current&&activeSessionRef.current&&!speechRecognition.current)void startRecordingRef.current();},350);}
 async function playAnswer(messageId:number,text:string,language:string,automatic=false){
   speechRun.current+=1;activeAudio.current?.pause();window.speechSynthesis?.cancel();setSpeaking(true);setVoiceFeedback("Speaking the AI answer…");
   if(automatic&&language!=="mr"){void browserSpeak(text,language);return;}
   let reply=audioReplies.current.get(messageId);
   if(!reply){
     try {const result=await api<{audio_base64:string|null;audio_mime:string|null;spoken_language:string}>(`/voice/messages/${messageId}/audio`);if(result.audio_base64){reply={base64:result.audio_base64,mime:result.audio_mime||"audio/mpeg",language:result.spoken_language};audioReplies.current.set(messageId,reply);}}
     catch { /* Browser speech remains available when server synthesis is unavailable. */ }
   }
   if(!reply){void browserSpeak(text,language);return;}
   const binary=atob(reply.base64),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
   const url=URL.createObjectURL(new Blob([bytes],{type:reply.mime})),audio=new Audio(url);
   activeAudio.current=audio;
   audio.onended=()=>{URL.revokeObjectURL(url);activeAudio.current=null;setSpeaking(false);setVoiceFeedback(null);resumeListening();};audio.onerror=()=>{URL.revokeObjectURL(url);activeAudio.current=null;void browserSpeak(text,reply.language);};
   audio.play().catch(()=>{URL.revokeObjectURL(url);activeAudio.current=null;setSpeaking(false);if(automatic)setVoiceFeedback("Answer ready. Press Play answer to hear it.");else void browserSpeak(text,reply.language);});
 }
 async function browserSpeak(text:string,lang:string){
   if(!window.speechSynthesis){setSpeaking(false);setVoiceFeedback("The answer is ready in the transcript. Press Play answer to hear it.");return;}
   const synth=window.speechSynthesis,run=++speechRun.current,languageCode=lang.split("-")[0].toLowerCase();synth.cancel();
   const voices=await availableSpeechVoices(synth);if(run!==speechRun.current)return;
   const voice=selectSpeechVoice(voices,languageCode),parts=speechChunks(speechText(text,languageCode));
   if(languageCode==="mr"&&!voice){setSpeaking(false);setVoiceFeedback("No Marathi or Hindi speech voice is available in this browser. Install an Indian language voice or read the transcript.");return;}
   setVoiceFeedback(languageCode==="mr"?(voice?.lang.toLowerCase().startsWith("mr")?"मराठी उत्तर वाचत आहे…":"हिंदी आवाजाच्या सहाय्याने मराठी उत्तर वाचत आहे…"):"Speaking the AI answer…");
   const speakPart=(index:number)=>{if(run!==speechRun.current)return;if(index>=parts.length){setSpeaking(false);setVoiceFeedback(null);resumeListening();return;}const utterance=new SpeechSynthesisUtterance(parts[index]);utterance.voice=voice;utterance.lang=voice?.lang||speechLocales[languageCode]||lang;utterance.rate=languageCode==="mr"?.88:.96;utterance.pitch=1;utterance.onend=()=>speakPart(index+1);utterance.onerror=event=>{if(event.error==="canceled"||event.error==="interrupted")return;setSpeaking(false);setVoiceFeedback("Speech playback could not use the selected language voice. The full answer remains in the transcript.");};synth.speak(utterance);};
   speakPart(0);
 }
 async function startCall(){setBusy(true);try{const next=await api<VoiceSession>("/voice/sessions",{method:"POST",body:JSON.stringify({vehicle_id:vehicleId||null,language})});setSession(next);activeSessionRef.current=true;setDetail(null);setClock("00:00");notify("Local AI voice session started");const greeting=next.messages?.find(item=>item.source==="GREETING");if(greeting)window.setTimeout(()=>{void playAnswer(greeting.id,greeting.text,greeting.language,true);},100);}catch(e){notify((e as Error).message);}finally{setBusy(false);}}
 async function finishCall(){if(!session)return;activeSessionRef.current=false;speechRecognition.current?.abort();speechRecognition.current=null;if(recorder.current?.state==="recording"){recorder.current.onstop=null;recorder.current.stop();stream.current?.getTracks().forEach(track=>track.stop());}setRecording(false);activeAudio.current?.pause();window.speechSynthesis?.cancel();setBusy(true);try{const completed=await api<VoiceSession>(`/voice/sessions/${session.id}/end`,{method:"POST"});setSession(completed);setDetail(completed);await load();notify("Call ended and structured notes were saved");}catch(e){notify((e as Error).message);}finally{setBusy(false);}}
 function appendTurn(turn:VoiceTurn){if(turn.audio_base64)audioReplies.current.set(turn.assistant.id,{base64:turn.audio_base64,mime:turn.audio_mime||"audio/wav",language:turn.spoken_language});setSession(current=>current?{...current,vehicle_id:turn.vehicle_id,messages:[...(current.messages||[]),turn.operator,turn.assistant]}:current);if(turn.rescue_mission){setLastRescue(turn.rescue_mission);void refresh();notify(`${turn.rescue_mission.replacement_vehicle_id} connected to Dispatch`);}setVoiceFeedback("Answer ready. Playing it now…");window.setTimeout(()=>playAnswer(turn.assistant.id,turn.assistant.text,turn.spoken_language,true),80);}
 async function submitQuestion(question:string){if(!session||!question.trim()||busy)return;setBusy(true);try{const turn=await api<VoiceTurn>(`/voice/sessions/${session.id}/message?fast=true`,{method:"POST",body:JSON.stringify({text:question.trim(),language})});appendTurn(turn);}catch(e){notify((e as Error).message);}finally{setBusy(false);}}
 async function sendText(){const question=draft.trim();if(!question)return;setDraft("");await submitQuestion(question);}
 async function upload(blob:Blob){if(!session)return;setBusy(true);setVoiceFeedback("Transcribing speech and checking live telemetry…");try{const form=new FormData();form.append("audio",blob,`turn.${blob.type.includes("mp4")?"mp4":"webm"}`);form.append("language",language);const turn=await apiForm<VoiceTurn>(`/voice/sessions/${session.id}/turn?fast=true`,form);appendTurn(turn);}catch(e){const message=(e as Error).message;setVoiceFeedback(message);notify(message);}finally{setBusy(false);}}
 async function startRecording(){
   if(!session||busy)return;
   try{
     activeAudio.current?.pause();window.speechSynthesis?.cancel();setSpeaking(false);setVoiceFeedback(null);
     if((speechMode==="browser"&&browserSpeechAvailable)||!runtime?.speech_to_text){
       const SpeechRecognition=browserSpeechConstructor();
       if(!SpeechRecognition)throw new Error("This browser does not provide speech recognition. Use Chrome or Edge, or type your question below.");
       const recognition=new SpeechRecognition();
       let finalText="",recognitionFailed=false,recognitionStarted=false,startupTimedOut=false,startupTimer:number|undefined;
       recognition.lang=speechLocales[language]||"hi-IN";recognition.continuous=false;recognition.interimResults=true;recognition.maxAlternatives=1;
       recognition.onstart=()=>{recognitionStarted=true;if(startupTimer)window.clearTimeout(startupTimer);setRecording(true);setVoiceFeedback("Listening through the browser microphone…");};
       recognition.onresult=event=>{let heard="";for(let i=event.resultIndex;i<event.results.length;i++){const text=event.results[i][0]?.transcript||"";heard+=text;if(event.results[i].isFinal)finalText+=text;}if(heard.trim())setVoiceFeedback(`Heard: ${heard.trim()}`);};
       recognition.onerror=event=>{if(startupTimer)window.clearTimeout(startupTimer);if(startupTimedOut)return;recognitionFailed=true;const denied=event.error==="not-allowed"||event.error==="service-not-allowed";const message=denied?"Microphone permission was denied. Allow microphone access, or type your question below.":"Browser speech recognition failed. Try again or switch to Local Whisper below.";setRecording(false);setVoiceFeedback(message);notify(message);};
       recognition.onend=()=>{if(startupTimer)window.clearTimeout(startupTimer);speechRecognition.current=null;setRecording(false);const question=finalText.trim();if(question&&activeSessionRef.current){setVoiceFeedback("Checking live telemetry…");void submitQuestion(question);}else if(!recognitionFailed&&activeSessionRef.current){setVoiceFeedback("No speech was detected. Press the microphone and try again.");}};
       speechRecognition.current=recognition;setRecording(true);setVoiceFeedback("Waiting for microphone access…");
       startupTimer=window.setTimeout(()=>{if(recognitionStarted||speechRecognition.current!==recognition)return;startupTimedOut=true;recognitionFailed=true;speechRecognition.current=null;recognition.abort();setRecording(false);const message="Browser speech recognition did not start. Check microphone permission, or type your question below.";setVoiceFeedback(message);notify(message);},6000);
       try{recognition.start();}catch(error){window.clearTimeout(startupTimer);speechRecognition.current=null;setRecording(false);throw error;}return;
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
 function stopRecording(){if(speechRecognition.current){const active=speechRecognition.current;setVoiceFeedback("Preparing your question…");active.stop();window.setTimeout(()=>{if(speechRecognition.current!==active)return;speechRecognition.current=null;active.abort();setRecording(false);setVoiceFeedback("No complete speech was detected. Try again, select the conversation language, or type your question below.");},2500);return;}if(recorder.current?.state==="recording"){setVoiceFeedback("Preparing the recording…");recorder.current.stop();}setRecording(false);}
 startRecordingRef.current=startRecording;
 async function openHistory(id:number){setBusy(true);try{setDetail(await api<VoiceSession>(`/voice/sessions/${id}`));}catch(e){notify((e as Error).message);}finally{setBusy(false);}}

 return <div className="voice-page">
   <div className="voice-runtime-strip">
    <span className={cn("runtime-dot",(runtime?.ready||runtime?.voices.mr||browserSpeechAvailable)&&"ready")}/><strong>{runtime?.ready?"Local voice intelligence ready":runtime?.voices.mr?"Marathi neural voice ready":browserSpeechAvailable?"Browser voice fallback ready":"Voice runtime unavailable"}</strong>
    <span><BrainCircuit size={13}/>{runtime?.ollama_model||"Qwen local model"}</span><span><Mic size={13}/>{speechMode==="browser"&&browserSpeechAvailable?"Fast browser recognition":runtime?.speech_to_text?(runtime.whisper_model||"Whisper"):"Typed questions"}</span><span><ShieldCheck size={13}/>Audio is not stored by ThermaTrace</span>
   </div>
   <div className="voice-layout">
    <Card className="voice-call-card">
      {!session||session.status!=="ACTIVE"?<div className="voice-start-state">
        <div className="voice-agent-mark"><div><Bot size={42}/><span/></div></div>
        <span className="eyebrow">THERMATRACE VOICE OPERATIONS</span><h2>Call the AI driver agent</h2><p>Select a vehicle, then ask about battery margin, container safety, route conditions, alerts, or destination reachability.</p>
        <div className="voice-config"><label>Vehicle context<select value={vehicleId} onChange={event=>setVehicleId(event.target.value)}>{data?.fleet.map(item=><option key={item.vehicle.vehicle_id} value={item.vehicle.vehicle_id}>{item.vehicle.vehicle_id} · {item.vehicle.vehicle_name}</option>)}</select></label><label>Conversation language<select value={language} onChange={event=>setLanguage(event.target.value)}>{voiceLanguages.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
        {browserSpeechAvailable&&runtime?.speech_to_text&&<label className="speech-mode">Microphone engine<select value={speechMode} onChange={event=>setSpeechMode(event.target.value as "browser"|"local")}><option value="browser">Fast browser recognition</option><option value="local">Private local Whisper</option></select></label>}
        {canCall?<Button onClick={startCall} disabled={busy||!vehicleId}><PhoneCall size={17}/>{busy?"Starting local agent…":"Start secure voice call"}</Button>:<div className="info-callout"><ShieldCheck size={18}/><p>Viewer accounts can review completed call notes. Admin or Operator access is required to start a conversation.</p></div>}
        <small><Database size={12}/> Answers are grounded in live SQL telemetry and timestamped operational records.</small>
      </div>:<div className="voice-active-state">
        <header><div><span className="eyebrow">ACTIVE LOCAL SESSION</span><h2>{session.vehicle_id||"Fleet operations"}</h2></div><div className="call-clock"><span/><Clock3 size={14}/>{clock}</div></header>
        <div className={cn("voice-orb",recording&&"listening",busy&&!recording&&"thinking")}><div><Headphones size={38}/></div>{[0,1,2,3,4,5,6].map(i=><i key={i}/>)}</div>
        <strong className="voice-state-label">{recording?"Listening…":speaking?"Speaking…":busy?"Checking live telemetry…":"AI driver agent connected"}</strong><p className="voice-instruction">{recording?"Speak naturally. The agent answers when you finish.":voiceFeedback||"Press the microphone and ask your next question."}</p>
        <div className="call-actions"><Button variant="outline" className="end-call" onClick={finishCall} disabled={busy}><PhoneOff size={17}/>End call</Button><button className={cn("mic-control",recording&&"active")} aria-label={recording?"Stop recording":"Start recording"} onClick={recording?stopRecording:startRecording} disabled={busy||!microphoneAvailable} title={microphoneAvailable?"Talk to the AI operations agent":"Use Chrome or Edge for microphone questions"}>{recording?<MicOff size={27}/>:<Mic size={27}/>}</button><span className="language-pill"><Languages size={14}/>{languageLabel(language)}</span></div>
        <div className="voice-mode-row"><label className="hands-free-toggle"><input type="checkbox" checked={handsFree} onChange={event=>setHandsFree(event.target.checked)}/> Hands-free turns: listen again after each answer</label>{browserSpeechAvailable&&runtime?.speech_to_text&&<select aria-label="Microphone engine" value={speechMode} onChange={event=>setSpeechMode(event.target.value as "browser"|"local")}><option value="browser">Fast browser speech</option><option value="local">Private local Whisper</option></select>}</div>
        <div className="voice-transcript" aria-live="polite">{!session.messages?.length&&<div className="voice-empty"><Sparkles size={18}/><p>Try “Kya yeh vehicle destination tak safely pahunch jayegi?”</p></div>}<AnimatePresence>{session.messages?.map(message=><motion.div initial={{opacity:0,y:5}} animate={{opacity:1,y:0}} key={message.id} className={cn("voice-message",message.role.toLowerCase())}><span>{message.role==="USER"?"YOU":"AI AGENT"} · {time(message.created_at)}</span><p>{message.text}</p>{message.role==="ASSISTANT"&&<button onClick={()=>playAnswer(message.id,message.text,message.language)} aria-label="Play answer"><Volume2 size={14}/>Play answer</button>}</motion.div>)}</AnimatePresence><div ref={messagesEnd}/></div>
        <div className="voice-text-fallback"><input value={draft} onChange={event=>setDraft(event.target.value)} onKeyDown={event=>{if(event.key==="Enter")sendText();}} placeholder="Type a question when a microphone is unavailable…"/><Button size="icon" onClick={sendText} disabled={busy||!draft.trim()} aria-label="Send typed question"><Send size={16}/></Button></div>
        {lastRescue&&<div className="voice-dispatch-link"><Truck size={16}/><span><strong>{lastRescue.replacement_vehicle_id}</strong> sent to Dispatch</span><Link href="/dispatch">Open Dispatch</Link></div>}
      </div>}
    </Card>
    <div className="voice-side-column">
      <Card className="voice-context-card"><div className="card-heading"><div><span className="eyebrow">LIVE CALL CONTEXT</span><h2>{selected?.vehicle.vehicle_id||"Select a vehicle"}</h2></div><Radio size={18}/></div>{selected?<><div className="context-risk"><div><span>AI risk score</span><strong>{selected.risk.risk_score}<small>/100</small></strong></div><Badge value={selected.risk.risk_level}/></div><div className="context-grid"><div><span>Battery SOC</span><strong>{selected.battery.soc.toFixed(1)}%</strong></div><div><span>Battery temp</span><strong>{selected.battery.battery_temperature.toFixed(1)}°C</strong></div><div><span>Container</span><strong>{selected.container.temperature.toFixed(1)}°C</strong></div><div><span>Distance left</span><strong>{selected.delivery.distance_remaining.toFixed(1)} km</strong></div></div><div className="voice-recommendation"><TriangleAlert size={16}/><p>{selected.risk.recommended_action}</p></div></>:<div className="empty">Vehicle context will appear here.</div>}</Card>
      <Card className="voice-privacy-card"><ShieldCheck size={20}/><div><strong>Privacy-aware voice</strong><p>{speechMode==="browser"&&browserSpeechAvailable?"Fast browser recognition may send speech to your browser provider. ThermaTrace stores the transcript and call note, never the raw audio. Choose Local Whisper for on-device recognition.":"Local Whisper runs on the configured ThermaTrace server; raw recordings are deleted after transcription. The first model load can take longer."}</p></div></Card>
      <Card className="voice-capability-card"><span className="eyebrow">ASK THE AGENT</span><h3>Live questions & actions</h3><div>{suggestedQuestions.map(question=><button key={question} disabled={!session||session.status!=="ACTIVE"||busy} onClick={()=>submitQuestion(question)}>{question}</button>)}</div><small>Answers use the selected vehicle and current database telemetry.</small></Card>
    </div>
   </div>
   <div className="voice-history-heading"><div><span className="eyebrow">CONVERSATION RECORDS</span><h2>Call notes & history</h2></div><span>{history.length} saved sessions</span></div>
   <div className="voice-history-layout"><div className="voice-history-list">{history.length?history.map(item=><button key={item.id} className={cn("voice-history-row",detail?.id===item.id&&"selected")} onClick={()=>openHistory(item.id)}><div className="history-icon"><History size={17}/></div><div><strong>{item.vehicle_id||"Fleet consultation"}</strong><p>{item.summary||"Conversation in progress"}</p><span>{new Date(item.started_at).toLocaleString()} · {item.language.toUpperCase()}</span></div><span className={cn("call-status",item.status.toLowerCase())}>{item.status}</span></button>):<div className="empty">Completed calls and their structured notes will appear here.</div>}</div>
    <Card className="voice-notes-card">{detail?<><div className="card-heading"><div><span className="eyebrow">AI-GENERATED CALL NOTE</span><h2>{detail.vehicle_id||"Fleet consultation"}</h2></div><CheckCircle2 size={20}/></div><p className="note-summary">{detail.summary||"End the active call to generate its final note."}</p><NoteGroup title="Topics" values={detail.notes.topics}/><NoteGroup title="Key telemetry at close" values={detail.notes.key_facts}/><NoteGroup title="Risks discussed" values={detail.notes.risks} warning/><NoteGroup title="Recommended follow-up" values={detail.notes.recommended_actions}/>{detail.messages&&<details><summary>View complete transcript</summary><div className="note-transcript">{detail.messages.map(message=><p key={message.id}><strong>{message.role==="USER"?"Operator":"AI Agent"}</strong>{message.text}</p>)}</div></details>}</>:<div className="voice-note-empty"><Database size={25}/><h3>Select a call record</h3><p>The closing summary, risks, telemetry facts, recommended actions, and complete transcript will appear here.</p></div>}</Card>
   </div>
 </div>;
}

function NoteGroup({title,values,warning=false}:{title:string;values?:string[];warning?:boolean}){if(!values?.length)return null;return <div className={cn("note-group",warning&&"warning")}><span>{title}</span>{values.map((value,index)=><p key={`${value}-${index}`}><i/>{value}</p>)}</div>;}
