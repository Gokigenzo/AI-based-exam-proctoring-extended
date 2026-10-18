"use client";
import { useEffect, useState } from "react";
import { Asset, client } from "@/lib/api";
export default function EvidencePlayer({asset,token}:{asset:Asset;token:string}){
  const [url,setUrl]=useState("");const [error,setError]=useState("");
  useEffect(()=>{setUrl("");setError("")},[asset.id]);
  async function open(){try{setError("");const data=await client(token)<{url:string}>(`/v1/assets/${asset.id}/view-url`);setUrl(data.url)}catch(e){setError(e instanceof Error?e.message:"Không tải được bằng chứng")}}
  const expired=asset.status==="expired"||new Date(asset.expires_at)<=new Date();
  if(expired)return <p className="muted">Bằng chứng đã hết hạn</p>;
  if(asset.status!=="ready")return <p className="muted">Bằng chứng chưa tải xong</p>;
  return <div className="evidence"><button className="subtle" onClick={open}>{url?"Làm mới liên kết":asset.content_type.startsWith("audio")?"▶ Nghe âm thanh gốc":"Mở bằng chứng"}</button>{url&&(asset.content_type.startsWith("video")?<video controls src={url} onError={()=>setError("Liên kết có thể đã hết hạn; hãy làm mới.")}/>:asset.content_type.startsWith("audio")?<audio controls src={url} onError={()=>setError("Liên kết có thể đã hết hạn; hãy làm mới.")}/>:<img src={url} alt="Ảnh bằng chứng của sự kiện"/>)}<p role="alert" className="error">{error}</p></div>
}
