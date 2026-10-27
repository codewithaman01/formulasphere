# FormulaSphere mobile app (Flutter)
    flutter create formulasphere_app
    cd formulasphere_app
    flutter pub add http flutter_math_fork flutter_secure_storage
    (replace lib/main.dart with the file here)
    flutter run                      # Android emulator; backend must be running
Real phone on the same Wi-Fi: flutter run --dart-define=API=http://YOUR_PC_IP:8000/api/v1
and start Django with: python manage.py runserver 0.0.0.0:8000 (add your PC IP to ALLOWED_HOSTS).
Android HTTP (non-HTTPS) testing: add android:usesCleartextTraffic="true" to <application> in android/app/src/main/AndroidManifest.xml.

The grade list on the sign-up screen is loaded from GET /api/v1/grades/, so adding or renaming a grade in the staff panel needs no app update.
