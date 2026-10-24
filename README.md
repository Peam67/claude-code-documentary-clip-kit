# 🎬 ให้ Claude Code ทำคลิปสไตล์สารคดี (ชุดเซตอัพ + สกิล)

คลิปแนว "คนพูดหน้ากล้อง → ผู้บรรยายเสียงทุ้ม → ภาพประกอบเปลี่ยนตามคำพูดทุกจังหวะ → ซับขึ้นทีละคำ → ตัวหนังสือใหญ่กระแทกจอ → จบด้วยการ์ดหนังเก่า + ปุ่ม CTA"
ที่เห็นตามรีล/ติ๊กต็อก ผมลองสั่ง **Claude Code** ทำให้ทั้งคลิปจนได้ไฟล์ mp4 จริง แล้วเก็บทุกอย่างที่ต้องติดตั้ง วิธีสั่ง และกับดักที่เจอมาไว้ที่นี่
ใครอยากลองทำเอง ก๊อปไปใช้ได้เลย

> ทำและทดสอบบน Windows 11 เครื่องเดียว (RTX 5060 Ti 8 GB) คลิปยาว ~50 วินาที เรนเดอร์ประมาณ 7 นาทีต่อเวอร์ชัน
> **ในรีโปนี้ไม่มีไฟล์วิดีโอ เพลง หรือภาพ** มีแค่สคริปต์ เอกสาร และสกิล

## มีอะไรในนี้

| โฟลเดอร์ | คืออะไร |
|---|---|
| `setup/SETUP_clip_maker.ps1` | สคริปต์ติดตั้งทีเดียวจบ: ลงโปรแกรมที่ขาด โหลดเครื่องมือ ฟอนต์ ติดตั้งสกิล แล้วเช็คคีย์ให้ |
| `skills/documentary-clip/` | **สกิลสำหรับ Claude Code**: ขั้นตอนทำคลิป + กับดักที่เจอ + คลังท่า motion เป็นตัวเลขทีละเฟรม + เครื่องมือเล็ก ๆ 2 ตัว |
| `examples/` | บทผู้บรรยายตัวอย่าง และข้อความสำเร็จรูปที่วางสั่ง Claude Code |

## ต้องมีอะไรบ้าง

| อะไร | ทำอะไร | ได้มาจากไหน |
|---|---|---|
| **Claude Code** (แอปเดสก์ท็อป) | สั่งงานทั้งหมด | [claude.ai/download](https://claude.ai/download) (ต้องมีบัญชีและแพ็กที่ใช้ Claude Code ได้) |
| Node.js 20+, FFmpeg, Python 3, Git | พื้นฐาน | สคริปต์ลงให้ถ้ายังไม่มี (ใช้ winget) |
| [HyperFrames](https://hyperframes.heygen.com) CLI + skills | ประกอบคลิปด้วย HTML แล้วเรนเดอร์เป็น mp4 | สคริปต์ลงให้ (npm) |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | ถอดเสียงพูดเพื่อทำซับ/จับจังหวะ | สคริปต์โหลดให้ |
| ฟอนต์ไทย Trirong + Kanit | ซับ คำใหญ่ ปุ่ม CTA | สคริปต์โหลดให้ |
| yt-dlp, pythainlp, edge-tts | โหลดคลิปฉากหนัง/เพลง, ตัดคำไทย, เสียงสำรอง | สคริปต์ลงให้ |
| **Pixabay API key** (ฟรี) | หาภาพ/วิดีโอสต็อก | คุณสมัครเอง (ข้างล่าง) |
| **ElevenLabs API key** (ฟรีได้) | เสียงผู้บรรยาย | คุณสมัครเอง (ข้างล่าง) |
| *ไม่บังคับ:* การ์ดจอ NVIDIA 8 GB+ | เสียงผู้บรรยายฟรีในเครื่อง (VoxCPM2) | ใส่ `-WithLocalVoice` ตอนรันสคริปต์ |

พื้นที่ว่าง: ตอนเรนเดอร์ใช้ไฟล์ชั่วคราว 1–2 GB ถ้าลงเสียงในเครื่องด้วยอีก ~20 GB (ลบแคชได้ทีหลัง)

## สิ่งที่คุณต้องทำเอง (ทีละขั้น)

### 1) ลง Claude Code
โหลดจาก [claude.ai/download](https://claude.ai/download) ล็อกอิน แล้วเปิดทิ้งไว้ก่อน

### 2) เอารีโปนี้มาไว้ในเครื่อง
แบบง่าย: กดปุ่มเขียว **Code → Download ZIP** แล้วแตกไฟล์
หรือใช้ git: `git clone <ลิงก์ของรีโปนี้>`

### 3) รันสคริปต์ติดตั้ง
เปิด **PowerShell** (ไม่ต้อง Run as administrator) ไปที่โฟลเดอร์ที่แตกไว้ แล้ววางคำสั่งนี้:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\SETUP_clip_maker.ps1
```

- ลงเฉพาะของที่ยังไม่มี รันซ้ำได้ ไม่ทับของเดิม ไม่แตะเวอร์ชัน Node/Python ที่คุณมีอยู่
- มีหน้าต่าง winget ถามยืนยันได้ ให้กดตกลง
- ตอนท้ายจะมีตารางสรุปว่าอะไรผ่าน/ไม่ผ่าน และเช็คคีย์ให้ (ถ้าตั้งคีย์แล้ว)
- อยากได้เสียงฟรีในเครื่องด้วย (ต้องมีการ์ดจอ NVIDIA): ต่อท้ายด้วย `-WithLocalVoice`
- ดูตัวเลือกอื่นได้ที่หัวไฟล์สคริปต์

### 4) เอา API key มาใส่ (ทำเอง 2 ตัว)

**Pixabay (ฟรี)**
1. สมัครที่ [pixabay.com](https://pixabay.com) แล้วล็อกอิน
2. ไปที่ [pixabay.com/api/docs](https://pixabay.com/api/docs/) จะเห็นคีย์ของคุณในหน้านั้น (ตัวอักษร/ตัวเลขยาว ๆ)
3. ใน PowerShell: `setx PIXABAY_API_KEY "วางคีย์ตรงนี้"`

**ElevenLabs (ฟรีได้ แต่มีเงื่อนไข)**
1. สมัครที่ [elevenlabs.io](https://elevenlabs.io) (อย่าสมัครผ่าน VPN/พร็อกซี และอย่าสมัครหลายบัญชี ระบบจะบล็อกบัญชีถาวร)
2. ในแดชบอร์ด หาเมนู **API Keys** แล้วสร้างคีย์ (ขึ้นต้นด้วย `sk_`)
3. ใน PowerShell: `setx ELEVENLABS_API_KEY "sk_วางคีย์ตรงนี้"`
4. เงื่อนไขของแพ็กฟรี: ใช้ได้เฉพาะ **เสียงสำเร็จรูป (premade)** เสียงจาก Voice Library เรียกผ่าน API ไม่ได้ และต้องใช้โมเดล `eleven_v3` เท่านั้น (โมเดลเก่าพูดไทยเป็นสำเนียงฝรั่ง) เครดิตฟรีประมาณ 10,000 ตัวอักษร (ดูยอดจริงในหน้าบัญชี) พอสำหรับคลิปสั้น ๆ ไม่กี่คลิป

> ❗ **ปิดแล้วเปิด PowerShell/Claude Code ใหม่** หลัง `setx` ตัวแปรถึงจะมีผล และ **อย่าเอาคีย์ไปวางในแชทหรือไฟล์ที่จะแชร์**

ไม่อยากใช้ ElevenLabs? เลือกเสียงฟรีในเครื่อง (ข้อ 3 `-WithLocalVoice`) หรือเสียง Edge TTS (`th-TH-NiwatNeural`) ที่ติดมากับสคริปต์ คุณภาพต่ำกว่า แต่ใช้ได้ทันที

### 5) สกิล
สคริปต์ในข้อ 3 ติดตั้งให้แล้ว 2 ชุด: สกิลของ HyperFrames (`hyperframes`, `media-use`, …) และสกิลของรีโปนี้ `documentary-clip`
ถ้าอยากติดตั้งเอง: ก๊อปโฟลเดอร์ `skills/documentary-clip` ไปไว้ที่ `%USERPROFILE%\.claude\skills\` แล้ว **ปิดเปิด Claude Code ใหม่**

### 6) สั่งทำคลิป
สร้างโฟลเดอร์ที่ **path สั้น ๆ** เช่น `D:\clips\เรื่องแรก` ใส่ไฟล์คลิปคนพูดหน้ากล้องลงไป เปิด Claude Code ในโฟลเดอร์นั้น แล้ววางข้อความจาก
[`examples/PROMPT_templates.md`](examples/PROMPT_templates.md) (แก้ชื่อไฟล์/เรื่อง/เพลงให้เป็นของคุณ)

## สกิลนี้ทำอะไร

`skills/documentary-clip/SKILL.md` เป็นคู่มือที่ Claude Code อ่านก่อนลงมือ: ลำดับงาน 10 ขั้น ตั้งแต่ตัดช่วงเงียบ เขียนบท ทำเสียง วางแผนภาพ หาภาพ ประกอบ ผสมเพลง ตรวจ จนถึงเรนเดอร์
พร้อมตารางกับดักที่เจอจริง เช่น ท่า invert เรนเดอร์ออกเป็นวงรีขาว, ภาพ HDR ทำให้สีเพี้ยนทั้งคลิป, ดิสก์เต็มตอนเรนเดอร์, Pixabay ตอบ 403
และ `references/motion-library.md` ที่สรุปท่า motion เป็นตัวเลขเฟรม (ซับ คำใหญ่ ตัวนับ ท่าเปลี่ยนภาพ คอลลาจ สโตรบ CTA) จากการวัดคลิปตัวอย่างทีละเฟรม
มีเครื่องมือสองตัว: `tighten_silence.py` (ตัดช่วงเงียบ) และ `eleven_tts_lines.py` (สร้างเสียงทีละบรรทัดแล้วเลือกรอบที่ถอดกลับถูกที่สุด)

## ปัญหาที่เจอบ่อย

| อาการ | แก้ |
|---|---|
| `File name too long` / เปิดเครื่องมือไม่ได้ | โฟลเดอร์ทำงาน path ยาวเกิน ย้ายไปที่สั้น ๆ เช่น `D:\clips\x` |
| เรนเดอร์ล้มเหลว เรื่องพื้นที่ดิสก์ | ตั้ง `TEMP` และ `TMP` ไปไดรฟ์ที่ว่างก่อนเรนเดอร์ |
| ElevenLabs `detected_unusual_activity` | บัญชีถูกบล็อก (มักเพราะ VPN/สมัครหลายบัญชี) แก้ไม่ได้ ต้องใช้บัญชีใหม่ที่ไม่ผ่าน VPN หรืออัปเกรดแพ็ก |
| ElevenLabs `paid_plan_required` / `voice_not_found` | ใช้เสียงจาก Library บนแพ็กฟรี ให้เปลี่ยนเป็นเสียง premade |
| Pixabay ตอบ 403 | ไม่ได้ส่ง `User-Agent` (Claude Code ทำให้เอง) |
| โหลดโมเดลเสียงในเครื่องแล้ว `paging file is too small` | หน่วยความจำว่างไม่พอ ให้ปิดโปรแกรมหนัก ๆ หรือให้ Claude Code โหลดน้ำหนักเข้าการ์ดจอตรง ๆ |
| คำอังกฤษ/ศัพท์เทคนิคออกเสียงเพี้ยน | สร้างหลายรอบแล้วเลือกรอบที่ถอดกลับถูกที่สุด หรือสะกดเป็นไทยให้ออกเสียงตามที่ต้องการ |

## ข้อจำกัดที่ควรรู้ (พูดตรง ๆ)

- **Claude Code ฟังเสียงไม่ได้** มันตรวจได้แค่ความดัง จังหวะ และถอดเสียงกลับด้วย whisper ว่าตรงบทไหม ส่วนรสนิยมของน้ำเสียงต้องคุณฟังเอง
- **ใช้เวลาและ token ไม่น้อย** โดยเฉพาะรอบแก้งาน ถ้าติดลิมิตง่าย ให้ข้ามการให้มันตรวจซ้ำหลายรอบ
- **ผลลัพธ์ไม่เหมือนต้นฉบับ 100%** ได้แนวคิดเดียวกัน (จังหวะ ท่า motion โครงเรื่อง) แต่ภาพประกอบเป็นของที่หาได้
- **ทดสอบแค่เครื่องเดียว** สคริปต์ติดตั้งรันผ่านบนเครื่องที่มีของครบอยู่แล้ว และทดสอบการดาวน์โหลดใหม่แยกส่วน แต่ยังไม่เคยรันบนเครื่องที่ว่างเปล่า ถ้าติดขัด เปิด Issue ได้
- **ลิขสิทธิ์:** ตัวอย่างใช้ฉากหนัง/เพลงที่มีลิขสิทธิ์ ซึ่งผมใช้ทำเล่น/ไม่เชิงพาณิชย์ ถ้าโพสต์ลง IG/TikTok/YouTube ระบบอาจปิดเสียงหรือเอาคลิปลง รับผิดชอบเองนะครับ รีโปนี้ไม่ได้แจกคลิปหรือเพลงใด ๆ
- ไม่มีความเกี่ยวข้องกับ Anthropic, HeyGen, ElevenLabs หรือ Pixabay เป็นแค่ชุดที่ผมรวมไว้ใช้เอง

## ขอบคุณเครื่องมือเหล่านี้

[HyperFrames](https://hyperframes.heygen.com) · [whisper.cpp](https://github.com/ggml-org/whisper.cpp) · [FFmpeg](https://ffmpeg.org) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [PyThaiNLP](https://github.com/PyThaiNLP/pythainlp) · [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2) (OpenBMB, Apache-2.0) · [Pixabay](https://pixabay.com) · [ElevenLabs](https://elevenlabs.io) · ฟอนต์ Trirong/Kanit (SIL OFL)

## English TL;DR

A Windows setup kit + a Claude Code skill for producing fast-cut "documentary style" Thai explainer clips with HyperFrames:
`setup/SETUP_clip_maker.ps1` installs the missing tools (ffmpeg, Node, Python, HyperFrames, whisper.cpp, Thai fonts) and the skill;
you bring a free Pixabay key and a free ElevenLabs key (premade voices + `eleven_v3` only), restart Claude Code and paste a prompt from `examples/`.
The skill documents the workflow, a frame-accurate motion library and the pitfalls we hit. Tested on one Windows 11 machine only.
No media is included; movie clips/songs are your responsibility.

## License

MIT (ดูไฟล์ `LICENSE`) ครอบคลุมสคริปต์และเอกสารในรีโปนี้ เครื่องมือและโมเดลที่สคริปต์ดาวน์โหลดมาเป็นไปตามไลเซนส์ของแต่ละตัว
