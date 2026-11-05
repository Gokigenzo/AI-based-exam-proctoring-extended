import type { Metadata } from "next";
import "./globals.css";
export const metadata:Metadata={title:"ExamWatch · Hồ sơ phòng thi",description:"Quan sát local, lưu bằng chứng và thẩm tra sự kiện phòng thi."};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="vi"><body>{children}</body></html>}
