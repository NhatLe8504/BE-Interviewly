# NHIỆM VỤ CHI TIẾT DÀNH CHO: LÊ ANH VŨ (Backend & Billing Specialist)

- **Mã sinh viên:** 28219032988
- **Email:** `vule556677@gmail.com`
- **Git Branch:** `vule556677`
- **Worktree BE:** `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE-vule556677`
- **Worktree FE:** `D:\DOANNHATLE\Interview_Coach_SRC_CODE\FE-vule556677`

---

## ⚠️ QUY TẮC BẮT BUỘC TRƯỚC KHI BẮT ĐẦU (GIT IDENTITY & WORKTREE)

1. Mở đúng thư mục worktree được phân công:
   - Backend: `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE-vule556677`
   - Frontend: `D:\DOANNHATLE\Interview_Coach_SRC_CODE\FE-vule556677`
2. Kiểm tra branch hiện tại:
   ```bash
   git branch --show-current
   ```
   *Kết quả phải đúng là: `vule556677`*
3. Cấu hình danh tính Git chính xác:
   ```bash
   git config user.name "vule556677"
   git config user.email "vule556677@gmail.com"
   ```
4. **Tuyệt đối KHÔNG commit trực tiếp lên nhánh `main`.** Chỉ push lên `vule556677` và tạo PR sang `main`.
5. 🛑 **QUY TẮC COMMIT & HỎI Ý KIẾN USER (BẮT BUỘC):**
   - Mỗi khi hoàn thành xong bất kỳ một task nhỏ hay bước nào (ví dụ: tạo xong entity, viết xong 1 service, pass 1 bộ test):
     - **TUYỆT ĐỐI KHÔNG TỰ Ý COMMIT NGAY.**
     - Chạy test kiểm tra trước (`pytest -q`).
     - Báo cáo ngắn gọn cho User: đã làm được gì, thay đổi những file nào, kết quả test ra sao.
     - **Hỏi ý kiến User:** *"Tôi đã hoàn thành task nhỏ này và test đã pass. Bạn có đồng ý để tôi commit không?"*
     - **CHỈ KHI USER XÁC NHẬN ĐỒNG Ý** mới được thực hiện `git add`, `git commit` và tạo PR!

---

## 🎯 PHẠM VI NHIỆM VỤ CỦA BẠN

Bạn chịu trách nhiệm về **Phân hệ Gói cước (Subscription), Cổng thanh toán trực tuyến (VNPay Sandbox HMAC-SHA512), Dịch vụ kết xuất Báo cáo PDF Backend (ReportLab), Hệ thống Audit Logs, và Giao diện Bảng giá/Thanh toán ở Frontend**.

---

## 📋 PHẦN 1: CÔNG VIỆC TẠI BACKEND (`BE-vule556677`)

### 1. Danh mục File cần triển khai:
```text
reference_app/app/
├── domain/
│   ├── billing.py               # Entity: SubscriptionPlan, UserSubscription, PaymentTransaction
│   └── audit.py                 # Entity: AuditLog, ModerationLog
├── application/
│   ├── billing/
│   │   ├── commands.py          # CreateCheckoutCommand, HandleWebhookCommand, CheckQuotaCommand
│   │   ├── ports.py             # SubscriptionRepoPort, PaymentTransactionRepoPort, PaymentGatewayPort
│   │   └── service.py           # SubscriptionService, PaymentService (xử lý đối soát, kích hoạt quyền Pro)
│   ├── report/
│   │   ├── ports.py             # PdfReportGeneratorPort
│   │   └── service.py           # PdfReportService (kết xuất file PDF và lưu trữ server)
│   └── audit/
│       ├── ports.py             # AuditLogRepoPort
│       └── service.py           # AuditLogService (ghi nhật ký thao tác dữ liệu)
├── infrastructure/
│   ├── payment/
│   │   ├── vnpay_adapter.py     # Tạo URL thanh toán VNPay HMAC-SHA512, đối soát chữ ký return & IPN
│   │   └── stripe_adapter.py    # Stripe Checkout Session adapter (dự phòng)
│   ├── report/
│   │   └── reportlab_pdf.py     # Thiết kế template PDF A4 đẹp mắt (Header, Rubric table, Speech stats, QR code)
│   └── persistence/
│       ├── billing_repository.py # SqlAlchemyBillingRepository
│       └── audit_repository.py   # SqlAlchemyAuditRepository
└── presentation/api/
    ├── routers/
    │   ├── billing.py           # GET /plans, POST /checkout, POST /vnpay-ipn, GET /subscriptions/me, GET /payments/history
    │   └── report.py            # GET /sessions/{id}/pdf/download
    └── schemas/
        ├── billing.py           # PlanOut, CheckoutIn, CheckoutUrlOut, PaymentTransactionOut, SubscriptionOut
        └── report.py            # PdfReportMetaOut
```

### 2. Các bước triển khai Backend:
1. **Domain & Entity:**
   - Xây dựng `domain/billing.py`: Định nghĩa `SubscriptionPlan` (Free, Pro Monthly, Pro Yearly), `UserSubscription` (active, expired, lượt còn lại), `PaymentTransaction` (pending, success, failed).
   - Invariant: Tiền tệ dùng `Decimal`, giá tiền >= 0.
2. **VNPay Sandbox Integration:**
   - Xây dựng `infrastructure/payment/vnpay_adapter.py`:
     - Tạo URL thanh toán VNPay kèm các tham số chuẩn (`vnp_Amount`, `vnp_Command`, `vnp_CreateDate`, `vnp_CurrCode: 'VND'`, `vnp_IpAddr`, `vnp_Locale: 'vn'`, `vnp_OrderInfo`, `vnp_OrderType`, `vnp_ReturnUrl`, `vnp_TmnCode`, `vnp_TxnRef`, `vnp_Version: '2.1.0'`).
     - Tạo mã hash `vnp_SecureHash` bằng thuật toán HMAC-SHA512.
     - Hàm xác thực chữ ký trả về từ VNPay (`validate_response()`).
3. **Application Service & Idempotent Webhook IPN:**
   - Xây dựng `application/billing/service.py`:
     - `create_checkout()`: Tạo transaction mới trạng thái `pending`.
     - `process_vnpay_ipn()`: Nhận IPN từ VNPay -> Kiểm tra chữ ký -> Nếu hợp lệ: Cập nhật transaction thành `success`, nâng cấp user lên `pro`, cộng lượt phỏng vấn, ghi nhận `audit_logs`.
     - **Cơ chế Idempotency:** Nếu transaction đã ở trạng thái `success`, không xử lý lặp lại, trả ngay `{"RspCode": "00", "Message": "Confirm Success"}` cho VNPay.
4. **Dịch vụ Báo cáo PDF:**
   - Xây dựng `infrastructure/report/reportlab_pdf.py`: Kết xuất báo cáo PDF khổ A4, hỗ trợ font tiếng Việt (Unicode), bao gồm thông tin ứng viên, bảng điểm Rubric 3 tiêu chí, biểu đồ chỉ số giọng nói WPM, mã QR code.
   - Endpoint: `GET /api/v1/sessions/{id}/pdf/download`.
5. **Đăng ký vào Container & Routers:**
   - Khai báo routers trong `presentation/api/routers/billing.py` và `report.py`.
   - Wire dependencies trong `bootstrap.py`.
   - Chạy test kiểm tra kiến trúc: `pytest tests/architecture/test_dependency_rule.py`.

---

## 📋 PHẦN 2: CÔNG VIỆC TẠI FRONTEND (`FE-vule556677`)

### 1. Danh mục File cần triển khai:
```text
src/
├── app/(user)/
│   ├── pricing/page.tsx                  # Bảng giá so sánh Free vs Pro (thay thế stub), Toggle tháng/năm, FAQ
│   └── subscription/
│       ├── my/page.tsx                   # Trang thông tin gói cá nhân: hạn mức còn lại, ngày hết hạn
│       ├── checkout/page.tsx             # Trang thanh toán: Tóm tắt đơn hàng, chọn cổng VNPay/MoMo/Stripe
│       ├── result/
│       │   ├── success/page.tsx          # Màn hình chúc mừng nâng cấp thành công, mã giao dịch
│       │   └── failed/page.tsx           # Màn hình báo lỗi thanh toán, lý do thất bại, nút thử lại
│       └── history/page.tsx              # Lịch sử các lần nạp gói, nút tải hóa đơn PDF
└── services/
    └── billingApi.ts                     # API client: fetchPlans(), createCheckout(), getSubscriptionStatus()
```

### 2. Các bước triển khai Frontend:
1. **Trang Bảng giá (`/pricing`):**
   - Thay thế stub hiện tại bằng bảng giá hoàn chỉnh:
     - Toggle chọn Trả theo tháng / Trả theo năm (tiết kiệm 20%).
     - Thẻ gói Free (0đ) và thẻ gói Pro (99.000đ/tháng, 899.000đ/năm).
     - Bảng đối soát chi tiết tính năng (Feature Comparison Table).
     - FAQ Accordion giải đáp thắc mắc thanh toán.
2. **Trang Checkout (`/subscription/checkout`):**
   - Đọc query param `?plan=pro_monthly` hoặc `pro_yearly`.
   - Hiển thị tóm tắt đơn vị tiền tệ VNĐ.
   - Lựa chọn phương thức thanh toán: VNPay (QR Pay / Thẻ ATM nội địa), MoMo, Stripe.
   - Bấm "Tiến hành thanh toán" -> Gọi `billingApi.createCheckout()` -> Nhận URL từ backend -> Chuyển hướng người dùng sang cổng VNPay.
3. **Trang Kết quả thanh toán (`/subscription/result/*`):**
   - `success/page.tsx`: Nhận params từ VNPay Return URL -> Xác thực trạng thái giao dịch với backend -> Hiển thị badge Pro, thông báo chúc mừng, nút "Bắt đầu phỏng vấn ngay".
   - `failed/page.tsx`: Hiển thị thông báo lỗi rõ ràng, gợi ý phương thức khác.
4. **Trang Lịch sử giao dịch (`/subscription/history`):**
   - Bảng danh sách các lần thanh toán, trạng thái và nút tải biên lai.

---

## 🚀 QUY TRÌNH ĐẨY CODE (PULL REQUEST)
```bash
# Tại worktree BE-vule556677
git add .
git commit -m "feat(billing): implement vnpay sandbox integration and pdf report service"
git push -u origin vule556677
gh pr create --base main --head vule556677 --title "feat(billing): VNPay Sandbox and PDF Generator" --body "Implement subscription plans, VNPay checkout, IPN webhook, and PDF skill reports."

# Tại worktree FE-vule556677
git add .
git commit -m "feat(pricing): implement pricing, checkout and subscription pages"
git push -u origin vule556677
gh pr create --base main --head vule556677 --title "feat(pricing): Pricing and Checkout flow" --body "Implement pricing comparison, checkout wizard, payment result screens, and history."
```
