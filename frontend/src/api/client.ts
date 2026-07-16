const BASE="/api";
async function post(path:string,body?:unknown):Promise<Response>{
  const headers:Record<string,string>={"Content-Type":"application/json"};
  const res=await fetch(`${BASE}${path}`,{method:"POST",headers,credentials:"same-origin",body:body?JSON.stringify(body):"{}"});
  if(res.status===401)window.dispatchEvent(new Event("auth-expired"));
  if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(data.detail||`请求失败 (${res.status})`)}
  return res;
}
async function uploadFile(path:string,file:File):Promise<Response>{
  const headers:Record<string,string>={};
  const form=new FormData();form.append("file",file);
  const res=await fetch(`${BASE}${path}`,{method:"POST",headers,credentials:"same-origin",body:form});
  if(res.status===401)window.dispatchEvent(new Event("auth-expired"));
  if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(data.detail||"上传失败")}
  return res;
}
export const api={
  post:(path:string,body?:unknown)=>post(path,body),
  upload:(path:string,file:File)=>uploadFile(path,file),
};
