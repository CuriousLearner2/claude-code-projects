import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email details
smtp_server = "smtp.mail.me.com"
smtp_port = 587
sender_email = "gautambiswas2004@icloud.com"
receiver_email = "gautambiswas2004@icloud.com"
import os
password = os.environ.get("EMAIL_PASSWORD")

subject = "[7th Grade Level] জামায়াতসহ ১১ দলের নতুন রাজনৈতিক আন্দোলন ও কর্মসূচি"
body = """
৭ম শ্রেণীর পাঠযোগ্য সংস্করণ: ১১ দলের রাজনৈতিক আন্দোলন

বাংলাদেশে জামায়াতে ইসলামী এবং আরও ১০টি রাজনৈতিক দল মিলে একটি শক্তিশালী জোট গঠন করেছে। এই ১১-দলীয় জোট এখন সরকারের ওপর চাপ সৃষ্টি করার জন্য বড় ধরনের আন্দোলনের প্রস্তুতি নিচ্ছে। তাদের প্রধান দাবি হলো, গত ফেব্রুয়ারি মাসে অনুষ্ঠিত গণভোটের রায় দ্রুত বাস্তবায়ন করা।

এই দলগুলোর মতে, গণভোটে দেশের মানুষ সংবিধান সংস্কারের পক্ষে রায় দিয়েছিল। নির্বাচনের সময় একটি নিয়ম ছিল যে, জয়ী প্রার্থীরা দুটি শপথ নেবেন—একটি সংসদ সদস্য হিসেবে এবং অন্যটি সংবিধান সংস্কার পরিষদের সদস্য হিসেবে। জামায়াত ও অন্যান্য বিরোধী দল দুটি শপথই গ্রহণ করলেও, বর্তমানে ক্ষমতায় থাকা বিএনপি নেতারা দ্বিতীয় শপথটি নেননি। এর ফলে সংবিধান সংস্কারের কাজ থমকে আছে।

আন্দোলনের অংশ হিসেবে এই জোট ইতিমধ্যে দেশের বিভিন্ন বিভাগে মিছিল ও সেমিনার করার পরিকল্পনা করেছে। তারা ২৫ এপ্রিল বিভাগীয় শহরগুলোতে এবং ২ মে জেলা শহরগুলোতে বিক্ষোভ মিছিল করবে। তাদের পরবর্তী লক্ষ্য হলো ঢাকা শহরে একটি 'মহাসমাবেশ' করা, যাতে সরকারের ওপর রাজনৈতিক চাপ আরও বাড়ানো যায়।

জোটের নেতারা হুঁশিয়ারি দিয়েছেন যে, সরকার যদি তাদের দাবি মেনে না নেয়, তবে সেপ্টেম্বর বা অক্টোবর মাস থেকে তারা আরও কঠোর কর্মসূচি যেমন—হরতাল বা অবরোধের দিকে যেতে পারেন। তারা চাইছেন সংসদের ভেতরে এবং রাজপথে—উভয় জায়গাতেই আন্দোলন চালিয়ে যেতে।
"""

# Create the email
msg = MIMEMultipart()
msg['From'] = sender_email
msg['To'] = receiver_email
msg['Subject'] = subject
msg.attach(MIMEText(body, 'plain', 'utf-8'))

try:
    # Connect and send
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(sender_email, password)
    server.sendmail(sender_email, receiver_email, msg.as_string())
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Error: {e}")
