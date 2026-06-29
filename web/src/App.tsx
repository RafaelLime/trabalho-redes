import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
	Activity, AlertCircle, CheckCircle2, Globe2, LogOut,
	MessageCircle, Plug, RefreshCcw, Send, Server, Users,
	Wifi, WifiOff,
} from 'lucide-react';
import './styles.css';

// Tipagem do eel para importação
declare global {
	interface Window {
		eel: any;
		receiveEvent: (event: any) => void;
		eel_expose: (func: any, name: string) => void;
	}
}

// Wrapper para as chamadas do Eel funcionarem com Async/Await de forma limpa
function eelCall(funcName: string, ...args: any[]): Promise<any> {
	return new Promise((resolve) => {
		if (window.eel && window.eel[funcName]) {
			window.eel[funcName](...args)((response: any) => resolve(response));
		} else {
			console.warn(`[Eel Mock] Função ${funcName} não encontrada no window.eel`);
			resolve({ status: 'ERROR', message: 'Eel não conectado' });
		}
	});
}

const mockState = {
	running: false,
	name: '',
	namespace: '',
	port: 4000,
	ttl: 3600,
	rdvHost: 'pyp2p.mfcaetano.cc',
	rdvPort: 8080,
	peers: [],
	messages: [],
};

function formatTime(value: string) {
	if (!value) return '';
	try {
		return new Intl.DateTimeFormat('pt-BR', {
			hour: '2-digit', minute: '2-digit', second: '2-digit'
		}).format(new Date(value));
	} catch {
		return value;
	}
}

function peerKey(peer: any) {
	return `${peer.name || 'peer'}@${peer.namespace || 'ns'}:${peer.ip}:${peer.port}`;
}

// Componentes visuais
function StatusPill({ running }: { running: boolean }) {
	return (
		<span className={`status-pill ${running ? 'online' : 'offline'}`}>
			{running ? <Wifi size={16} /> : <WifiOff size={16} />}
			{running ? 'Online' : 'Offline'}
		</span>
	);
}

// Props da interface do SetupPanel
interface SetupPanelProps { config: any; setConfig: any; onStart: () => void; loading: boolean; error: string; }
function SetupPanel({ config, setConfig, onStart, loading, error }: SetupPanelProps) {

	return (
		<section className="panel setup-panel">
			<div className="panel-heading">
				<div>
					<p className="eyebrow">Configuração local</p>
					<h2>Entrar no chat P2P</h2>
				</div>
				<Plug className="heading-icon" />
			</div>

			<div className="form-grid">
				<label>
					Nome do peer
					<input value={config.name} onChange={(e) => setConfig({ ...config, name: e.target.value })} placeholder="alice" />
				</label>
				<label>
					Namespace / sala
					<input value={config.namespace} onChange={(e) => setConfig({ ...config, namespace: e.target.value })} placeholder="redes" />
				</label>
				<label>
					Porta P2P local
					<input type="number" value={config.port} onChange={(e) => setConfig({ ...config, port: Number(e.target.value) })} />
				</label>
				<label>
					TTL, em segundos
					<input type="number" value={config.ttl} onChange={(e) => setConfig({ ...config, ttl: Number(e.target.value) })} />
				</label>
				<label className="wide">
					Servidor Rendezvous
					<input value={config.rdvHost} onChange={(e) => setConfig({ ...config, rdvHost: e.target.value })} />
				</label>
				<label>
					Porta Rendezvous
					<input type="number" value={config.rdvPort} onChange={(e) => setConfig({ ...config, rdvPort: Number(e.target.value) })} />
				</label>
			</div>

			{error && <div className="alert"><AlertCircle size={18} /> {error}</div>}

			<button className="primary-btn" onClick={onStart} disabled={loading}>
				{loading ? <RefreshCcw className="spin" size={18} /> : <CheckCircle2 size={18} />}
				{loading ? 'Iniciando...' : 'Iniciar peer'}
			</button>
		</section>
	);
}

// Props da interface do PeerList
interface PeerListProps { peers: any[]; selectedPeer: any; setSelectedPeer: any; onRefresh: () => void; disabled: boolean; }
function PeerList({ peers, selectedPeer, setSelectedPeer, onRefresh, disabled }: PeerListProps) {

	return (
		<section className="panel peers-panel">
			<div className="panel-heading compact">
				<div>
					<p className="eyebrow">Descoberta</p>
					<h3>Peers ativos</h3>
				</div>
				<button className="icon-btn" onClick={onRefresh} disabled={disabled} title="Atualizar peers">
					<RefreshCcw size={17} />
				</button>
			</div>
			<div className="peers-list">
				{peers.length === 0 ? (
					<div className="empty-state">
						<Users size={28} />
						<p>Nenhum peer encontrado ainda.</p>
					</div>
				) : peers.map((peer) => (
					<button
						key={peerKey(peer)}
						className={`peer-card ${selectedPeer && peerKey(selectedPeer) === peerKey(peer) ? 'selected' : ''}`}
						onClick={() => setSelectedPeer(peer)}
					>
						<div className="avatar">{(peer.name || '?').slice(0, 1).toUpperCase()}</div>
						<div>
							<strong>{peer.name}@{peer.namespace}</strong>
							<span>{peer.ip}:{peer.port} - {peer.state}</span>
						</div>
					</button>
				))}
			</div>
		</section>
	);
}

// Props da interface do ChatPanel
interface ChatPanelProps { running: boolean; selectedPeer: any; messages: any[]; onSend: (t: string) => void; onBroadcast: (t: string) => void; }
function ChatPanel({ running, selectedPeer, messages, onSend, onBroadcast }) {

	const [text, setText] = useState('');
	const [chatMode, setChatMode] = useState('direct');
	const [broadcastScope, setBroadcastScope] = useState('*');
	const scrollRef = useRef(null);

	useEffect(() => {
		scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
	}, [messages.length, chatMode]);

	const visibleMessages = useMemo(() => {
		return messages.filter((m) => {
			if (chatMode === 'broadcast') {
				// Mostra mensagens que você enviou pra sala ou que vieram com a tag de broadcast
				return m.to?.includes('Salas') || m.from?.includes('[BROADCAST]');
			} else {
				// Se não tem peer selecionado, não mostra nada na aba direta
				if (!selectedPeer) return false;
				const peerId = `${selectedPeer.name}@${selectedPeer.namespace}`;
				// Mostra apenas mensagens enviadas/recebidas deste peer exato
				return m.from === peerId || m.to === peerId;
			}
		});
	}, [messages, chatMode, selectedPeer]);

	async function submit() {
		const value = text.trim();
		if (!value) return;
		setText('');

		if (chatMode === 'broadcast') {
			// Garante que o scope comece com # se não for o asterisco global
			let finalScope = broadcastScope.trim();
			if (finalScope !== '*' && !finalScope.startsWith('#')) {
				finalScope = `#${finalScope}`;
			}
			await onBroadcast(finalScope, value);
		} else {
			await onSend(value);
		}
	}

	return (
		<section className="panel chat-panel">

			{/* Novas Abas de Navegação */}
			<div className="chat-tabs" style={{ display: 'flex', gap: '10px', padding: '15px 20px 0', borderBottom: '1px solid #2a2a35' }}>
				<button
					onClick={() => setChatMode('direct')}
					style={{ padding: '8px 16px', background: chatMode === 'direct' ? '#2563eb' : 'transparent', border: 'none', color: '#fff', borderRadius: '6px 6px 0 0', cursor: 'pointer' }}>
					Privado
				</button>
				<button
					onClick={() => setChatMode('broadcast')}
					style={{ padding: '8px 16px', background: chatMode === 'broadcast' ? '#2563eb' : 'transparent', border: 'none', color: '#fff', borderRadius: '6px 6px 0 0', cursor: 'pointer' }}>
					Salas (PUB)
				</button>
			</div>

			<div className="chat-header">
				<div>
					<p className="eyebrow">{chatMode === 'direct' ? 'Mensagem Direta' : 'Mensagem Pública'}</p>
					<h3>
						{chatMode === 'direct'
							? (selectedPeer ? `${selectedPeer.name}@${selectedPeer.namespace}` : 'Selecione um peer na lista')
							: 'Broadcast Global e Namespaces'
						}
					</h3>
				</div>
				{chatMode === 'broadcast' ? <Globe2 className="heading-icon" /> : <MessageCircle className="heading-icon" />}
			</div>

			<div className="messages">
				{visibleMessages.length === 0 ? (
					<div className="empty-state center">
						<MessageCircle size={38} />
						<p>{chatMode === 'direct' ? 'Nenhuma mensagem direta ainda.' : 'Nenhuma mensagem pública recebida.'}</p>
					</div>
				) : visibleMessages.map((message) => (
					<div key={message.id || `${message.timestamp}-${message.text}`} className={`message ${message.direction === 'out' ? 'out' : 'in'}`}>
						<div className="bubble">
							<div className="message-meta">
								{/* No broadcast, é importante ver de quem veio */}
								<strong>{message.direction === 'out' ? 'Você' : message.from}</strong>
								<span>{formatTime(message.timestamp)}</span>
							</div>
							<p>{message.text}</p>
						</div>
					</div>
				))}
				<div ref={scrollRef} />
			</div>

			<div className="composer" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
				{chatMode === 'broadcast' && (
					<input
						style={{ width: '120px' }}
						value={broadcastScope}
						onChange={(e) => setBroadcastScope(e.target.value)}
						placeholder="* ou namespace"
						disabled={!running}
						title="Digite * para todos ou CIC para um namespace específico"
					/>
				)}
				<input
					style={{ flex: 1 }}
					value={text}
					onChange={(e) => setText(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === 'Enter' && !e.shiftKey) submit();
					}}
					placeholder={chatMode === 'direct' ? "Digite sua mensagem..." : "Mensagem para a sala..."}
					disabled={!running || (chatMode === 'direct' && !selectedPeer)}
				/>
				<button onClick={submit} disabled={!running || !text.trim() || (chatMode === 'direct' && !selectedPeer)} title="Enviar Mensagem">
					<Send size={18} />
				</button>
			</div>
		</section>
	);
}

// Função para renderizar o painel de logs
function LogsPanel({ logs }: { logs: any[] }) {

	return (
		<section className="panel logs-panel">
			<div className="panel-heading compact">
				<div>
					<p className="eyebrow">Observabilidade</p>
					<h3>Eventos</h3>
				</div>
				<Activity className="heading-icon small" />
			</div>
			<div className="logs-list">
				{logs.length === 0 ? <p className="muted">Sem eventos ainda.</p> : logs.slice(-7).reverse().map((log, index) => (
					<div className={`log-row ${log.level || 'info'}`} key={`${log.timestamp}-${index}`}>
						<span>{formatTime(log.timestamp)}</span>
						<p>{log.message}</p>
					</div>
				))}
			</div>
		</section>
	);
}

// Função principal do aplicativo
function App() {
	const [status, setStatus] = useState<any>(mockState);
	const [config, setConfig] = useState({
		name: 'alice',
		namespace: 'redes',
		port: 4000,
		ttl: 3600,
		rdvHost: 'pyp2p.mfcaetano.cc', // Altere pro seu RDV padrão
		rdvPort: 8080,
	});
	const [selectedPeer, setSelectedPeer] = useState<any>(null);
	const [messages, setMessages] = useState<any[]>([]);
	const [logs, setLogs] = useState<any[]>([]);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState('');

	function pushLog(level: string, message: string, details?: any) {
		setLogs((prev) => [...prev, { level, message, details, timestamp: new Date().toISOString() }]);
	}

	useEffect(() => {

		if (window.eel) {
			console.log("EEL disponível");
		}

		// Registra a função global para o Python conseguir chamar
		window.receiveEvent = (event: any) => {
			if (event.type === 'PEERS_UPDATED') setStatus((prev: any) => ({ ...prev, peers: event.peers || [] }));
			if (event.type === 'MESSAGE_RECEIVED' || event.type === 'MESSAGE_SENT') setMessages((prev) => [...prev, event.message]);
			if (event.type === 'STATUS_CHANGED') setStatus(event.status || mockState);
			if (event.type === 'LOG') setLogs((prev) => [...prev, event]);
		};

		// Diz pro eel expor nossa window.receiveEvent
		if (window.eel && window.eel.expose) {
			window.eel.expose(window.receiveEvent, 'receiveEvent');
		}

		// Carrega o estado inicial do Python
		eelCall('get_status').then((data) => {
			if (data && data.running) {
				setStatus(data);
				setConfig((prev) => ({
					...prev,
					name: data.name || prev.name,
					namespace: data.namespace || prev.namespace,
					port: data.port || prev.port,
					ttl: data.ttl || prev.ttl,
				}));
			}
		});
	}, []);

	async function startPeer() {
		setError('');
		setLoading(true);
		try {
			const response = await eelCall('start_peer', config);
			if (response.status !== 'OK') {
				setError(response.message || 'Falha ao iniciar peer.');
			} else {
				setStatus(response.peer);
				setMessages([]); // Limpa chat anterior
			}
		} catch (err) {
			setError(String(err));
		} finally {
			setLoading(false);
		}
	}

	async function stopPeer() {
		const response = await eelCall('stop_peer');
		if (response.status === 'OK') {
			setStatus((prev: any) => ({ ...prev, running: false, peers: [] }));
			setSelectedPeer(null);
		}
	}

	async function refreshPeers() {
		await eelCall('discover_peers');
	}

	async function sendDirect(text: string) {
		if (!selectedPeer) return;
		const response = await eelCall('send_message', selectedPeer, text);
		if (response.status !== 'OK') pushLog('error', response.message || 'Falha ao enviar mensagem.');
	}

	async function sendBroadcast(scope, text: string) {
		const response = await eelCall('broadcast_message', scope, text);
		if (response.status !== 'OK') pushLog('error', response.message || 'Falha no broadcast.');
	}

	return (
		<main className="app-shell">
			<header className="hero">
				<div>
					<p className="eyebrow">Trabalho de Redes</p>
					<h1>Chat P2P</h1>
					<p className="hero-subtitle">Interface React embutida em Python com Eel, conectando ao Rendezvous por TCP.</p>
				</div>
				<div className="hero-actions">
					<StatusPill running={status.running} />
					{status.running && <button className="danger-btn" onClick={stopPeer}><LogOut size={17} /> Sair</button>}
				</div>
			</header>

			<section className="identity-bar">
				<div><Server size={18} /><span>RDV</span><strong>{config.rdvHost}:{config.rdvPort}</strong></div>
				<div><Users size={18} /><span>Peer</span><strong>{status.name ? `${status.name}@${status.namespace}` : 'não iniciado'}</strong></div>
				<div><Plug size={18} /><span>Porta P2P</span><strong>{status.port || config.port}</strong></div>
			</section>

			{!status.running ? (
				<SetupPanel config={config} setConfig={setConfig} onStart={startPeer} loading={loading} error={error} />
			) : (
				<div className="workspace-grid">
					<div className="left-column">
						<PeerList peers={status.peers || []} selectedPeer={selectedPeer} setSelectedPeer={setSelectedPeer} onRefresh={refreshPeers} disabled={!status.running} />
						<LogsPanel logs={logs} />
					</div>
					<ChatPanel running={status.running} selectedPeer={selectedPeer} messages={messages} onSend={sendDirect} onBroadcast={sendBroadcast} />
				</div>
			)}
		</main>
	);
}

export default App;