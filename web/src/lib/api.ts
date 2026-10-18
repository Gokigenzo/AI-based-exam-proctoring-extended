export type Asset = {id:string;content_type:string;status:string;expires_at:string};
export type ExamEvent = {id:string;session_id:string;source_id:string;track_id:string|null;kind:string;started_at:string;ended_at:string;review_status:string;model_version:string;model_confidence:number|null;details:Record<string,unknown>;assets:Asset[]};
export type Speech = {id:string;event_id:string|null;source_id:string;started_at:string;ended_at:string;transcript_raw:string|null;transcript_corrected:string|null;processing_status:string;expired:boolean;assets:Asset[]};
export type Session = {id:string;name:string;started_at:string;ended_at:string|null};
export type Device = {id:string;name:string;revoked:boolean;last_seen:string|null;status:Record<string,unknown>};
export type Review = {id:string;verdict:string;note:string;created_at:string;user_id:string};
export const labels:Record<string,string>={expression_observation:"Biểu cảm cần xem xét",speech_detected:"Có tiếng nói",rising:"Nhổm / ngồi dậy",standing:"Đứng",side_lean:"Nghiêng người",turned:"Quay đầu / thân"};
export const verdicts:Record<string,string>={pending:"Chưa thẩm tra",confirmed:"Đã xác nhận",dismissed:"Đã loại cảnh báo",needs_review:"Cần xem thêm"};
export function date(value:string){return new Intl.DateTimeFormat("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",dateStyle:"short",timeStyle:"medium"}).format(new Date(value));}
export function client(token:string){return async function api<T>(path:string,body?:unknown,method?:string,signal?:AbortSignal):Promise<T>{
  const base=process.env.NEXT_PUBLIC_API_URL||"http://127.0.0.1:8000";
  const response=await fetch(base+path,{method:method||(body===undefined?"GET":"POST"),headers:{Authorization:`Bearer ${token}`,...(body===undefined?{}:{"Content-Type":"application/json"})},body:body===undefined?undefined:JSON.stringify(body),signal,cache:"no-store"});
  if(!response.ok){const data=await response.json().catch(()=>({detail:"Máy chủ chưa phản hồi"}));throw Error(typeof data.detail==="string"?data.detail:`Yêu cầu lỗi (${response.status})`);}
  return response.json();
};}
