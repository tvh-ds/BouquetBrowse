import { locale } from "@/lib/locale";
import { LoginForm } from "@/components/login-form";
export default async function Login() {
  const lang = await locale();
  return (
    <main id="main" className="page-width login-layout">
      <section className="login-intro">
        <h1>
          {lang === "vi"
            ? "Một nơi nhỏ,\nđể tìm điều đẹp đẽ."
            : "A little space for\nsomething lovely."}
        </h1>
        <p>
          {lang === "vi"
            ? "Khám phá những bó hoa ở Hà Nội và nhìn giá quảng cáo với nhiều góc nhìn hơn."
            : "Discover Hanoi bouquets and see advertised prices with a little more perspective."}
        </p>
        <p className="demo-note">
          {process.env.APP_MODE !== "pilot"
            ? lang === "vi"
              ? "Bản minh họa: người bán, ảnh tạo bằng AI, giá và lịch sử đều hư cấu."
              : "Demonstration: fictional sellers, AI-generated photos, prices and history."
            : lang === "vi"
              ? "Bản nghiên cứu riêng tư. Chỉ người được mời mới có thể truy cập."
              : "Private research pilot. Access is restricted to invited participants."}
        </p>
      </section>
      <LoginForm lang={lang} demo={process.env.APP_MODE !== "pilot"} />
    </main>
  );
}
