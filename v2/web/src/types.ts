export type Row = Record<string, unknown>;
export type Evidence = {kind: 'records'|'document';title:string;records?:unknown;text?:string;document_id?:string;queried_at?:string;source?:string;approval_status?:string};
export type Message = {role:'user'|'assistant';text:string;evidence?:Evidence[];mode?:string};
export type Document = {document_id:string;filename:string;content?:string;text?:string;status?:string};
export type Workspace = {lots:Record<string,string>[];tables:{table:string;label:string;count:number}[];questions:Record<string,string[]>;dashboard:Record<string,number>;ai_available:boolean;local_ai:boolean};
export async function api<T>(path:string, init?:RequestInit):Promise<T>{
 const response=await fetch(path,init);const body=await response.json();
 if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'요청을 처리하지 못했습니다. 입력과 연결 상태를 확인해 주세요.');
 return body as T;
}
export function readStored<T>(key:string,fallback:T):T {try{return JSON.parse(sessionStorage.getItem(key)||'null')??fallback}catch{return fallback}}
export function saveStored(key:string,value:unknown){try{sessionStorage.setItem(key,JSON.stringify(value))}catch{/* Storage can be unavailable in private browsers. */}}
