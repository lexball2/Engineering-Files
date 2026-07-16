import { api } from "./client";
export type UserRole = "guest" | "employee" | "admin";
export interface AuthResponse { username:string; role:UserRole }
export const authApi={
  register:(u:string,p:string)=>api.post("/auth/register",{username:u,password:p}).then(r=>r.json()as Promise<AuthResponse>),
  login:(u:string,p:string)=>api.post("/auth/login",{username:u,password:p}).then(r=>r.json()as Promise<AuthResponse>),
  guestLogin:()=>api.post("/auth/guest-login").then(r=>r.json()as Promise<AuthResponse>)
};
