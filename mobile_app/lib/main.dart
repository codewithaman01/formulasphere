import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

// Android emulator reaches your PC at 10.0.2.2. Use your PC's IP on a real phone, or an https URL in production.
const base = String.fromEnvironment('API', defaultValue: 'http://10.0.2.2:8000/api/v1');
const store = FlutterSecureStorage();
String? token;

Future<http.Response> api(String path, {Map<String, dynamic>? body}) {
  final h = {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Token $token'};
  final u = Uri.parse('$base$path');
  return body == null ? http.get(u, headers: h) : http.post(u, headers: h, body: jsonEncode(body));
}

String errors(String body) {
  try {
    final d = jsonDecode(body);
    if (d is Map) return d.values.expand((v) => v is List ? v : [v]).join('\n');
  } catch (_) {}
  return 'Something went wrong. Check your connection and try again.';
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  token = await store.read(key: 'token');
  runApp(MaterialApp(
    title: 'FormulaSphere',
    theme: ThemeData(colorSchemeSeed: const Color(0xFF4F46E5), useMaterial3: true),
    home: token == null ? const AuthPage() : const ListPage(),
  ));
}

class AuthPage extends StatefulWidget {
  const AuthPage({super.key});
  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final user = TextEditingController(), email = TextEditingController(), pass = TextEditingController();
  // The grade list comes from the server (Grades in the staff panel), so the app never hard-codes it.
  List<Map<String, dynamic>> grades = [];
  String? grade;
  bool register = false, busy = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    loadGrades();
  }

  Future<void> loadGrades() async {
    try {
      final res = await api('/grades/');
      if (res.statusCode == 200 && mounted) {
        setState(() => grades = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>());
      }
    } catch (_) {}
  }

  Future<void> submit() async {
    setState(() { busy = true; error = ''; });
    final res = await api(register ? '/auth/register/' : '/auth/login/', body: {
      'username': user.text.trim(), 'password': pass.text,
      if (register) ...{'email': email.text.trim(), 'grade': grade},
    });
    if (res.statusCode == 200 || res.statusCode == 201) {
      token = jsonDecode(res.body)['token'];
      await store.write(key: 'token', value: token);
      if (!mounted) return;
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const ListPage()));
    } else {
      setState(() { error = errors(res.body); busy = false; });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(register ? 'Create account' : 'Sign in')),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          TextField(controller: user, decoration: const InputDecoration(labelText: 'Username')),
          if (register) TextField(controller: email, decoration: const InputDecoration(labelText: 'Email')),
          if (register)
            DropdownButtonFormField<String>(
              value: grade, decoration: const InputDecoration(labelText: 'Grade'),
              items: grades.map((g) => DropdownMenuItem<String>(value: g['slug'] as String, child: Text(g['name'] as String))).toList(),
              onChanged: (v) => setState(() => grade = v)),
          TextField(controller: pass, obscureText: true, decoration: const InputDecoration(labelText: 'Password')),
          if (error.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error, style: const TextStyle(color: Colors.red))),
          const SizedBox(height: 16),
          FilledButton(onPressed: busy ? null : submit, child: Text(register ? 'Create account' : 'Sign in')),
          TextButton(onPressed: () => setState(() => register = !register),
              child: Text(register ? 'I already have an account' : 'Create an account')),
        ]),
      );
}

class ListPage extends StatefulWidget {
  const ListPage({super.key});
  @override
  State<ListPage> createState() => _ListPageState();
}

class _ListPageState extends State<ListPage> {
  List items = [];
  bool loading = true;
  String error = '';

  @override
  void initState() { super.initState(); load(''); }

  Future<void> load(String q) async {
    setState(() { loading = true; error = ''; });
    final res = await api('/formulas/?q=${Uri.encodeComponent(q)}');
    setState(() {
      loading = false;
      if (res.statusCode == 200) { items = jsonDecode(res.body)['results']; } else { error = errors(res.body); }
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Formulas'), actions: [
          IconButton(icon: const Icon(Icons.logout), tooltip: 'Sign out', onPressed: () async {
            await store.delete(key: 'token'); token = null;
            if (!context.mounted) return;
            Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const AuthPage()));
          })]),
        body: Column(children: [
          Padding(padding: const EdgeInsets.all(12), child: TextField(
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search formulas', border: OutlineInputBorder()),
            onSubmitted: load)),
          if (loading) const LinearProgressIndicator(),
          if (error.isNotEmpty) Padding(padding: const EdgeInsets.all(12), child: Text(error)),
          Expanded(child: items.isEmpty && !loading
              ? const Center(child: Text('No formulas found for your grade.'))
              : ListView.builder(itemCount: items.length, itemBuilder: (_, i) {
                  final f = items[i];
                  return ListTile(
                    title: Text(f['title']),
                    subtitle: SingleChildScrollView(scrollDirection: Axis.horizontal, child: Math.tex(f['latex'], onErrorFallback: (_) => Text(f['latex']))),
                    trailing: f['locked'] == true ? const Icon(Icons.lock_outline) : null,
                    onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => DetailPage(f['slug']))));
                })),
        ]),
      );
}

class DetailPage extends StatelessWidget {
  final String slug;
  const DetailPage(this.slug, {super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(),
        body: FutureBuilder<http.Response>(
          future: api('/formulas/$slug/'),
          builder: (_, snap) {
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final res = snap.data!;
            if (res.statusCode == 403) {
              return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(
                  '${jsonDecode(res.body)['detail']}\nContact the site owner to activate Premium on your account.', textAlign: TextAlign.center)));
            }
            if (res.statusCode != 200) return Center(child: Text(errors(res.body)));
            final f = jsonDecode(res.body);
            return ListView(padding: const EdgeInsets.all(16), children: [
              Text(f['title'], style: Theme.of(context).textTheme.headlineSmall),
              if (f['is_demo'] == true) const Text('Demo record, not expert reviewed', style: TextStyle(color: Colors.orange)),
              Padding(padding: const EdgeInsets.symmetric(vertical: 16), child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal, child: Math.tex(f['latex'], textStyle: const TextStyle(fontSize: 26)))),
              Text(f['short_explanation']),
              if ((f['detailed_explanation'] ?? '').isNotEmpty) Text(f['detailed_explanation']),
              if ((f['variables'] as List).isNotEmpty) ...[
                const Padding(padding: EdgeInsets.only(top: 16), child: Text('Variables', style: TextStyle(fontWeight: FontWeight.bold))),
                for (final v in f['variables']) ListTile(dense: true, leading: Math.tex(v['symbol']), title: Text(v['name']),
                    subtitle: (v['unit'] as String).isEmpty ? null : Math.tex(v['unit']))],
              if ((f['derivation_steps'] as List).isNotEmpty) ...[
                const Padding(padding: EdgeInsets.only(top: 16), child: Text('Derivation', style: TextStyle(fontWeight: FontWeight.bold))),
                for (final s in f['derivation_steps']) ListTile(title: Math.tex(s['latex']), subtitle: Text(s['explanation']))],
            ]);
          }),
      );
}
