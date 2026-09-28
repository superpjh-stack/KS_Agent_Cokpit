import {useCallback,useEffect,useRef,useState} from 'react';
import type {Evidence} from '../types';

export type RealtimeVoiceState='idle'|'permission'|'connecting'|'listening'|'speaking'|'responding'|'error';
type Turn={role:'user'|'assistant';text:string};

export function useRealtimeVoice(token:string,lot:string,onTurn:(turn:Turn)=>void,onEvidence:(items:Evidence[])=>void){
 const [state,setState]=useState<RealtimeVoiceState>('idle'),[error,setError]=useState(''),[muted,setMuted]=useState(false),[needsPlay,setNeedsPlay]=useState(false);
 const pc=useRef<RTCPeerConnection|null>(null),channel=useRef<RTCDataChannel|null>(null),media=useRef<MediaStream|null>(null),audio=useRef<HTMLAudioElement|null>(null),epoch=useRef(0);
 const pending=useRef<AbortController|null>(null);
 const toolCalls=useRef(new Set<string>());
 const evidenceCallback=useRef(onEvidence);evidenceCallback.current=onEvidence;
 const assistantText=useRef(''),callback=useRef(onTurn);callback.current=onTurn;
 const supported=window.isSecureContext&&!!navigator.mediaDevices?.getUserMedia&&typeof RTCPeerConnection!=='undefined';

 const stop=useCallback(()=>{
  epoch.current++;pending.current?.abort();pending.current=null;
  channel.current?.close();channel.current=null;
  pc.current?.close();pc.current=null;
  media.current?.getTracks().forEach(t=>t.stop());media.current=null;
  if(audio.current){audio.current.pause();audio.current.srcObject=null;audio.current.remove()}audio.current=null;
  assistantText.current='';toolCalls.current.clear();setMuted(false);setNeedsPlay(false);setError('');setState('idle');
 },[]);
 useEffect(()=>()=>stop(),[stop]);
 useEffect(()=>{stop()},[token,lot,stop]);

 const play=useCallback(async()=>{if(!audio.current)return;try{await audio.current.play();setNeedsPlay(false)}catch{setNeedsPlay(true);setError('소리가 준비됐습니다. 재생을 눌러 주세요.')}},[]);
 function finishAssistant(text?:string){const final=(text||assistantText.current).trim();assistantText.current='';if(final)callback.current({role:'assistant',text:final})}
 async function runTool(name:string,callId:string,argumentsText:string,run:number){
  if(run!==epoch.current||toolCalls.current.has(callId))return;toolCalls.current.add(callId);setState('responding');
  let args:Record<string,unknown>={};
  try{args=JSON.parse(argumentsText||'{}') as Record<string,unknown>}catch{args={}}
  let output:string;
  try{
   const response=await fetch('/api/realtime/tool',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({name,arguments:args})});
   const payload=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(String(payload.detail||'제조 기록 조회 호출에 실패했습니다.'));
   if(run===epoch.current&&payload.evidence?.length)evidenceCallback.current(payload.evidence);
   output=String(payload.output||JSON.stringify({error:'빈 도구 응답'}));
  }catch(e){output=JSON.stringify({error:(e as Error).message})}
  if(run!==epoch.current||channel.current?.readyState!=='open')return;
  channel.current.send(JSON.stringify({type:'conversation.item.create',item:{type:'function_call_output',call_id:callId,output}}));
  channel.current.send(JSON.stringify({type:'response.create'}));
 }
 function handleEvent(raw:string,run:number){
  if(run!==epoch.current)return;
  try{
   const event=JSON.parse(raw) as Record<string,unknown>,type=String(event.type||'');
   if(type==='input_audio_buffer.speech_started'){setState('speaking')}
   else if(type==='input_audio_buffer.speech_stopped')setState('responding');
   else if(type==='conversation.item.input_audio_transcription.completed'){
    const transcript=String(event.transcript||'').trim();if(transcript){callback.current({role:'user',text:transcript})}
   }else if(type==='response.output_audio_transcript.delta')assistantText.current+=String(event.delta||'');
   else if(type==='response.output_audio_transcript.done')finishAssistant(String(event.transcript||''));
   else if(type==='response.function_call_arguments.done')void runTool(String(event.name||''),String(event.call_id||''),String(event.arguments||'{}'),run);
   else if(type==='response.done'){finishAssistant();setState('listening')}
   else if(type==='error'){const detail=event.error as Record<string,unknown>|undefined;stop();setError(String(detail?.message||'실시간 음성 연결에 문제가 생겼습니다.'));setState('error')}
  }catch{/* Ignore unknown provider events; audio continues over WebRTC. */}
 }
 async function start(){
  if(state!=='idle'&&state!=='error')return;
  stop();const run=epoch.current;setError('');
  if(!supported){setError('이 브라우저에서는 실시간 마이크를 사용할 수 없습니다. HTTPS 또는 localhost에서 열어 주세요.');setState('error');return}
  setState('permission');
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(run!==epoch.current){stream.getTracks().forEach(t=>t.stop());return}media.current=stream;
   const peer=new RTCPeerConnection();pc.current=peer;
   const player=document.createElement('audio');player.autoplay=true;player.setAttribute('playsinline','');audio.current=player;
   peer.ontrack=e=>{player.srcObject=e.streams[0];void play()};
   peer.onconnectionstatechange=()=>{if(run!==epoch.current)return;if(['failed','disconnected'].includes(peer.connectionState)){stop();setError('실시간 음성 연결이 끊겼습니다. 다시 시작해 주세요.');setState('error')}else if(peer.connectionState==='connected')setState('listening')};
   stream.getTracks().forEach(t=>peer.addTrack(t,stream));
   const dc=peer.createDataChannel('oai-events');channel.current=dc;dc.onmessage=e=>handleEvent(String(e.data),run);dc.onopen=()=>{if(run===epoch.current)setState('listening')};
   setState('connecting');const controller=new AbortController();pending.current=controller;const offer=await peer.createOffer();await peer.setLocalDescription(offer);if(run!==epoch.current)return;
   const params=new URLSearchParams();if(lot)params.set('lot_id',lot);
   const response=await fetch('/api/realtime/session'+(params.size?'?'+params:''),{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/sdp',Authorization:'Bearer '+token},body:offer.sdp});
   const answer=await response.text();if(!response.ok){let message='실시간 음성 세션을 시작하지 못했습니다.';try{message=JSON.parse(answer).detail||message}catch{}throw new Error(message)}
   if(run!==epoch.current)return;await peer.setRemoteDescription({type:'answer',sdp:answer});
  }catch(e){if(run===epoch.current){const message=(e as Error).name==='NotAllowedError'?'마이크 권한을 허용해 주세요.':(e as Error).message;stop();setError(message);setState('error')}}
 }
 function toggleMute(){const next=!muted;media.current?.getAudioTracks().forEach(t=>{t.enabled=!next});setMuted(next)}
 return {state,error,muted,needsPlay,supported,start,stop,toggleMute,play,active:!['idle','error'].includes(state)};
}
