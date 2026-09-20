export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response=await fetch(`/api${path}`,{...options,credentials:"include",headers:{"Content-Type":"application/json",...options?.headers},cache:"no-store"});
  if (!response.ok) { const body=await response.json().catch(()=>({detail:"Unable to connect to the API"})); throw new Error(typeof body.detail === "string" ? body.detail : "Check the supplied values and try again"); }
  return response.json();
}

export async function apiDownload(path:string,filename:string) {
  const response=await fetch(`/api${path}`,{credentials:"include",cache:"no-store"});
  if(!response.ok){const body=await response.json().catch(()=>({detail:"Unable to generate the file"}));throw new Error(typeof body.detail==="string"?body.detail:"Unable to generate the file");}
  const blob=await response.blob(),url=URL.createObjectURL(blob),anchor=document.createElement("a");
  anchor.href=url;anchor.download=filename;document.body.appendChild(anchor);anchor.click();anchor.remove();URL.revokeObjectURL(url);
}

export async function apiForm<T>(path:string,form:FormData):Promise<T>{
  const response=await fetch(`/api${path}`,{method:"POST",body:form,credentials:"include",cache:"no-store"});
  if(!response.ok){const body=await response.json().catch(()=>({detail:"Unable to process microphone audio"}));throw new Error(typeof body.detail==="string"?body.detail:"Unable to process microphone audio");}
  return response.json();
}
