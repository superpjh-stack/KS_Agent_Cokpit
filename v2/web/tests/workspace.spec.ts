import {test,expect} from '@playwright/test';

test('documents, records, suggestions, history and scoped chat',async({page},info)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'현장의 질문, 기록으로 답하다.'})).toBeVisible();
 if(info.project.name==='mobile')await page.getByRole('button',{name:'자료',exact:true}).click();
 await page.getByRole('textbox',{name:'문서 검색'}).fill('금형');
 await page.locator('.document-list button').first().click();
 await expect(page.locator('dialog[open] .document-body')).toContainText('금형');
 await page.getByRole('button',{name:'문서 닫기'}).click();
 await page.getByRole('button',{name:'데이터허브',exact:true}).click();
 await page.locator('.left-panel select').selectOption('dies');
 await expect(page.locator('.table-records')).toContainText('DIE-310');
 if(info.project.name==='mobile')await page.getByRole('button',{name:'자료 닫기'}).click();
 await page.getByLabel('작업지시 / 소재 LOT').selectOption('WO-260901');
 await page.getByRole('textbox',{name:'질문 입력'}).fill('설비 측정값을 보여줘');
 await page.getByRole('button',{name:'질문 보내기'}).click();
 await expect(page.locator('.evidence')).toBeVisible();
 await page.locator('.evidence summary').first().click();
 await expect(page.locator('.evidence')).toContainText('DIE-101');
 await expect(page.locator('.evidence')).not.toContainText('DIE-310');
 await page.getByLabel('작업지시 / 소재 LOT').selectOption('WO-260903');
 await expect(page.locator('.evidence')).toHaveCount(0);
 if(info.project.name==='mobile')await page.getByRole('button',{name:'질문',exact:true}).click();
 await page.locator('.history-list button').first().click();
 await expect(page.getByLabel('작업지시 / 소재 LOT')).toHaveValue('WO-260901');
 await expect(page.locator('.evidence')).toBeVisible();
 await page.getByRole('button',{name:'새 대화',exact:true}).click();
 await page.getByLabel('작업지시 / 소재 LOT').selectOption('');
 if(info.project.name==='mobile')await page.getByRole('button',{name:'질문',exact:true}).click();
 await page.locator('.suggestions button').first().click();
 await expect(page.locator('.evidence')).toBeVisible();
 await page.getByRole('button',{name:'설정',exact:true}).click();
 await page.getByLabel('AI 접근 코드').fill('ui-test-code');
 await page.getByRole('button',{name:'저장',exact:true}).click();
 await expect(page.locator('dialog[open]')).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 expect(errors).toEqual([]);
 await page.getByRole('button',{name:'새 대화',exact:true}).click();
 await page.screenshot({path:`test-results/${info.project.name}.png`,fullPage:true});
});

test('late response cannot enter a new work order',async({page})=>{
 let release:()=>void=()=>{};
 const gate=new Promise<void>(resolve=>{release=resolve});
 await page.route('**/api/chat',async route=>{await gate;await route.fulfill({json:{text:'STALE_RESPONSE',evidence:[],mode:'demo'}}).catch(()=>{})});
 await page.goto('/');
 await page.getByRole('textbox',{name:'질문 입력'}).fill('측정값');
 await page.getByRole('button',{name:'질문 보내기'}).click();
 await expect(page.locator('.loading')).toBeVisible();
 await page.getByLabel('작업지시 / 소재 LOT').selectOption('WO-260902');
 release();
 await expect(page.locator('.loading')).toHaveCount(0);
 await expect(page.locator('.messages')).not.toContainText('STALE_RESPONSE');
});

test('microphone permission failure is recoverable',async({page})=>{
 await page.addInitScript(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Permission denied','NotAllowedError')}});
 await page.goto('/');
 await page.getByRole('button',{name:'실시간 음성',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('마이크 권한');
 await expect(page.getByRole('button',{name:'실시간 음성',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'새 대화',exact:true}).click();
 await expect(page.getByRole('alert')).toHaveCount(0);
});

test('voice mute, interruption, disconnect and cleanup use the current session',async({page})=>{
 await page.addInitScript(()=>{
  const state={enabled:true,stopped:0,closed:0,channel:null as any,peer:null as any};
  (window as any).__voice=state;
  const track={get enabled(){return state.enabled},set enabled(value:boolean){state.enabled=value},stop(){state.stopped++}};
  navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]}) as unknown as MediaStream;
  class Peer {
   connectionState='connected';onconnectionstatechange:(()=>void)|null=null;
   ontrack:any=null;
   constructor(){state.peer=this}
   addTrack(){}
   createDataChannel(){const dc={readyState:'open',onmessage:null as any,onopen:null as any,send(){},close(){state.closed++}};state.channel=dc;return dc}
   async createOffer(){return {type:'offer',sdp:'fake-offer'}}
   async setLocalDescription(){}
   async setRemoteDescription(){state.channel.onopen?.()}
   close(){state.closed++}
  }
  (window as any).RTCPeerConnection=Peer;
 });
 await page.route('**/api/realtime/session*',route=>route.fulfill({contentType:'application/sdp',body:'fake-answer'}));
 await page.goto('/');
 await page.getByRole('button',{name:'실시간 음성',exact:true}).click();
 await expect(page.locator('.voice-status')).toContainText('듣고 있어요');
 await page.getByRole('button',{name:'음소거',exact:true}).click();
 expect(await page.evaluate(()=>(window as any).__voice.enabled)).toBe(false);
 await page.getByRole('button',{name:'음소거 해제',exact:true}).click();
 expect(await page.evaluate(()=>(window as any).__voice.enabled)).toBe(true);
 await page.evaluate(()=>(window as any).__voice.channel.onmessage({data:JSON.stringify({type:'input_audio_buffer.speech_started'})}));
 await expect(page.locator('.voice-status')).toContainText('말씀을 듣고 있어요');
 await page.getByRole('button',{name:'종료',exact:true}).click();
 expect(await page.evaluate(()=>(window as any).__voice.stopped)).toBe(1);
 await page.getByRole('button',{name:'실시간 음성',exact:true}).click();
 await expect(page.locator('.voice-status')).toContainText('듣고 있어요');
 await page.evaluate(()=>{const peer=(window as any).__voice.peer;peer.connectionState='failed';peer.onconnectionstatechange()});
 await expect(page.getByRole('alert')).toContainText('연결이 끊겼습니다');
 expect(await page.evaluate(()=>(window as any).__voice.stopped)).toBe(2);
 await page.getByRole('button',{name:'실시간 음성',exact:true}).click();
 await expect(page.locator('.voice-status')).toContainText('듣고 있어요');
 await page.getByLabel('작업지시 / 소재 LOT').selectOption('WO-260902');
 await expect(page.locator('.voice-status')).toHaveCount(0);
 expect(await page.evaluate(()=>(window as any).__voice.stopped)).toBe(3);
});
