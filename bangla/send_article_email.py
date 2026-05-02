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

subject = "সহজ ভাষায় সংবাদ: ১১টি দলের নতুন আন্দোলন"
body = """
সহজ ভাষায় খবর: ১১টি দলের নতুন আন্দোলন

জামায়াতে ইসলামী এবং আরও ১০টি ছোট দল মিলে একটি জোট তৈরি করেছে। তারা সবাই মিলে এখন বড় একটি আন্দোলন করার কথা ভাবছে। তাদের দাবি হলো, গত ফেব্রুয়ারি মাসে দেশে একটি ভোট হয়েছিল। সেই ভোটে মানুষ যা চেয়েছিল, সরকার যেন দ্রুত তা মেনে কাজ শুরু করে।

এই দলগুলো এখন দেশের বিভিন্ন শহরে মিছিল করছে। তারা মানুষের কাছে গিয়ে ছোট ছোট লিফলেট বা কাগজ দিচ্ছে। এই কাগজে তাদের দাবির কথা লেখা আছে। তারা চায় সরকার যেন দেশের বড় বড় নিয়মগুলো বদলে ফেলে।

আগে কথা ছিল, যারা নির্বাচনে জিতবে তারা দুটি শপথ নেবে। একটি হলো সাধারণ নিয়ম মেনে চলার জন্য, অন্যটি দেশের নিয়ম বদলানোর জন্য। কিন্তু এখন যারা সরকারে আছে, তাদের নেতারা দ্বিতীয় শপথটি নেননি। এই কারণে অন্য দলগুলো বলছে যে সরকার তাদের কথা রাখছে না।

জামায়াত ও অন্য দলগুলো বলছে, সরকার যদি তাদের দাবি না মানে, তবে তারা সামনে আরও বড় আন্দোলন করবে। তারা ঢাকা শহরে অনেক মানুষকে নিয়ে একটি বড় সভা করতে চায়। তারা চায় সাধারণ মানুষও যেন তাদের এই কাজে সাহায্য করে। 

এখন দেখার বিষয় সরকার কী করে। যদি সরকার তাদের কথা না শোনে, তবে এই আন্দোলন আরও অনেক দিন চলতে পারে। দলগুলো বলছে, তারা সাধারণ মানুষের অধিকার আদায়ের জন্য রাজপথে লড়াই করবে।
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
    server.starttls() # Secure the connection
    server.login(sender_email, password)
    server.sendmail(sender_email, receiver_email, msg.as_string())
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Error: {e}")
