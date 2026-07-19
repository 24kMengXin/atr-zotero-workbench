/* global IOUtils, PathUtils */
var ATRZoteroWorkbench = {
	id: null,
	rootURI: null,
	observerID: null,
	sectionID: null,
	readingNoteSectionID: null,
	readingNoteID: null,
	readingContextItemID: null,
	workspaceOverride: null,
	activeWorkspace: null,
	activeGraph: null,
	activeNativeMap: null,
	activeReviewQueue: null,
	activeRunName: null,
	activeRunRecord: null,
	activeCollectionID: null,
	activeOverviewCollectionID: null,
	activeKnowledgeCollectionID: null,
	activeResearchCollectionID: null,
	activeSourceCollectionID: null,
	activeHistoryCollectionID: null,
	lastHumanInput: new Map(),
	suppressedNotifierItemIDs: new Set(),
	writeQueues: new Map(),
	pendingSourceImports: new Map(),
	dockRenderLogged: false,
	companionWindow: null,
	companionFocusNode: null,
	companionItem: null,
	defaultWorkspace: "/Users/zone/Documents/research assistant/atr-zotero-workbench/output/multilingual-agent-action-continuation",
	defaultRegistry: "/Users/zone/Documents/research assistant/atr-zotero-workbench/output/runs.json",

	init({ id, rootURI }) {
		this.id = id;
		this.rootURI = rootURI;
	},

	log(message) {
		Zotero.debug("ATR Workbench: " + message);
	},

	get configuredWorkspace() {
		return Zotero.Prefs.get("extensions.atr-zotero-workbench.workspace", true);
	},

	get registryPath() {
		return Zotero.Prefs.get("extensions.atr-zotero-workbench.registry", true)
			|| this.defaultRegistry;
	},

	inboxPath() {
		return PathUtils.join(this.activeWorkspace || this.defaultWorkspace, "human-input", "inbox.jsonl");
	},

	runtimeLogPath() {
		return PathUtils.join(this.activeWorkspace || this.defaultWorkspace, "plugin-runtime.jsonl");
	},

	async appendWorkspaceLine(path, line) {
		let previous = this.writeQueues.get(path) || Promise.resolve();
		let current = previous.catch(() => {}).then(async () => {
			await Zotero.File.createDirectoryIfMissingAsync(PathUtils.parent(path), {
				ignoreExisting: true,
			});
			let existing = "";
			try {
				existing = await Zotero.File.getContentsAsync(path);
			}
			catch (_) {
				// The audit file is created on first use.
			}
			await Zotero.File.putContentsAsync(path, existing + line + "\n");
		});
		this.writeQueues.set(path, current);
		try {
			await current;
		}
		finally {
			if (this.writeQueues.get(path) === current) this.writeQueues.delete(path);
		}
	},

	async appendRuntimeStatus(stage, details = {}) {
		let record = {
			schema_version: "0.2",
			component: "zotero_native_projection",
			stage,
			at: new Date().toISOString(),
			...details,
		};
		this.log(stage + ": " + JSON.stringify(details));
		try {
			await this.appendWorkspaceLine(this.runtimeLogPath(), JSON.stringify(record));
		}
		catch (error) {
			this.log("could not write runtime status: " + error);
		}
	},

	async appendHumanInput(record) {
		let stableRecord = { ...record };
		delete stableRecord.at;
		delete stableRecord.notifier;
		// Zotero's Note Editor can emit a second modify notification that only
		// wraps/normalizes the same HTML. Formatting-only rewrites are not a new
		// cognitive review event; text, stance, locator and ATR target changes are.
		if (stableRecord.event === "human_note_modified" && stableRecord.note_html) {
			stableRecord.note_html = this.plainNote(stableRecord.note_html);
		}
		let signature = JSON.stringify(stableRecord);
		let key = record.zotero_note_key || record.zotero_annotation_key;
		if (key && this.lastHumanInput.get(key) === signature) return;
		if (key) this.lastHumanInput.set(key, signature);
		try {
			await this.appendWorkspaceLine(this.inboxPath(), JSON.stringify(record));
		}
		catch (error) {
			this.log("could not write human input: " + error);
		}
	},

	async readJsonFile(path, fallback = {}) {
		try {
			return JSON.parse(await Zotero.File.getContentsAsync(path));
		}
		catch (_) {
			return fallback;
		}
	},

	async loadRunRegistry() {
		let registry = await this.readJsonFile(this.registryPath, { runs: [] });
		if (registry.schema_version !== "0.2"
			|| registry.selection_policy !== "EXPLICIT_ACTIVATION_ONLY"
			|| registry.selection?.mode !== "EXPLICIT"
			|| registry.selection?.selected_key !== registry.active_run) {
			throw new Error("ATR registry 缺少 v0.2 显式 authority selection；拒绝按构建顺序猜测当前 topic");
		}
		for (let run of registry.runs || []) {
			for (let field of ["controller_kind", "authority_path", "authority_scope", "view_role"]) {
				if (!run[field]) throw new Error("ATR registry run " + run.key + " 缺少 " + field);
			}
		}
		return {
			activeRun: registry.active_run || null,
			runs: (registry.runs || []).filter(run => run.key && run.workspace),
			selection: registry.selection,
		};
	},

	async defaultRun() {
		let registry = await this.loadRunRegistry();
		let configured = this.workspaceOverride || this.configuredWorkspace;
		if (configured) {
			return registry.runs.find(run => run.workspace === configured)
				|| { key: PathUtils.filename(configured), label: PathUtils.filename(configured), workspace: configured };
		}
		let selected = registry.runs.find(run => run.key === registry.activeRun);
		if (!selected) throw new Error("显式 active_run 未解析到已登记 topic");
		return selected;
	},

	async portfolioRun() {
		let registry = await this.loadRunRegistry();
		let selected = registry.runs.find(run => run.key === registry.activeRun);
		if (!selected) throw new Error("显式 portfolio authority 未解析到已登记 run");
		return selected;
	},

	async runForProgramNode(node) {
		if (node?.kind !== "research_program" || !node.data?.child_run_id) {
			throw new Error("所选节点没有可导航的 child authority");
		}
		let registry = await this.loadRunRegistry();
		let run = registry.runs.find(candidate => candidate.run_id === node.data.child_run_id);
		if (!run) {
			throw new Error("program 的 child_run_id 未解析到 registry：" + node.data.child_run_id);
		}
		if (run.view_role !== "REGISTERED_V2_RUN") {
			throw new Error("program 节点只能进入 REGISTERED_V2_RUN，实际为：" + run.view_role);
		}
		return run;
	},

	async openProgramNode(node) {
		let run = await this.runForProgramNode(node);
		let synced = await this.openTopic(run, Zotero.getMainWindow());
		if (!synced) return null;
		this.companionFocusNode = (this.activeGraph?.nodes || [])
			.find(candidate => candidate.kind === "research_problem")
			|| (this.activeGraph?.nodes || []).find(candidate => candidate.kind === "atr_v2_subject" && candidate.data?.active)
			|| null;
		this.companionItem = synced.note;
		if (this.companionWindowAlive()) await this.renderCompanionWindow();
		await this.appendRuntimeStatus("portfolio_program_opened", {
			program_node_id: node.id,
			child_run_id: node.data.child_run_id,
			workspace: run.workspace,
			interaction: "PORTFOLIO_TO_NATIVE_TOPIC_TAB",
		});
		return synced;
	},

	async openProgramReviewNode(node) {
		let synced = await this.openProgramNode(node);
		if (!synced) return null;
		let review = (this.activeGraph?.nodes || []).find(candidate =>
			candidate.kind === "collision_review"
			&& candidate.data?.review_id === node.data?.collision_review_artifact_id
		) || (this.activeGraph?.nodes || []).find(candidate => candidate.kind === "collision_review");
		if (!review) throw new Error("child topic 尚无可导航的 collision-review artifact");
		let object = (this.activeNativeMap?.objects || []).find(candidate => candidate.graph_node_id === review.id);
		if (!object?.marker) throw new Error("collision review 尚无 Zotero native mapping");
		let note = await this.findMarkedNote(object.marker);
		if (!note) throw new Error("collision review Note 尚未物化");
		await this.openNativeNote(await this.ensureOwnerRouteReviewTemplate(note));
		this.companionFocusNode = review;
		this.companionItem = note;
		if (this.companionWindowAlive()) await this.renderCompanionWindow();
		await this.appendRuntimeStatus("portfolio_program_owner_review_opened", {
			program_node_id: node.id,
			child_run_id: node.data.child_run_id,
			collision_review_node_id: review.id,
			interaction: "PORTFOLIO_TO_CHILD_COLLISION_REVIEW_NOTE",
		});
		return note;
	},

	async openPortfolio() {
		return this.openTopic(await this.portfolioRun(), Zotero.getMainWindow());
	},

	async loadProjection(run) {
		let workspace = run?.workspace || this.defaultWorkspace;
		let graph = JSON.parse(await IOUtils.readUTF8(PathUtils.join(workspace, "graph.json")));
		let nativeMap = JSON.parse(await IOUtils.readUTF8(PathUtils.join(workspace, "zotero", "native-projection.json")));
		if (nativeMap.schema_version !== "0.1" || nativeMap.projection !== "atr-zotero-native-map"
			|| nativeMap.run !== graph.run) {
			throw new Error("native-projection.json 与 graph.json 不一致；请先重建显式 Zotero 映射");
		}
		let graphIDs = new Set((graph.nodes || []).map(node => node.id));
		let sourceIDs = new Set((graph.nodes || [])
			.filter(node => node.kind === "paper" && node.data?.source_id)
			.map(node => node.data.source_id));
		let objectIDs = new Set();
		let markers = new Set();
		let topicNotes = 0;
		for (let object of nativeMap.objects || []) {
			if (!object.object_id || objectIDs.has(object.object_id)) {
				throw new Error("Zotero 映射包含空白或重复 object_id: " + object.object_id);
			}
			objectIDs.add(object.object_id);
			if (!object.marker || markers.has(object.marker)) {
				throw new Error("Zotero 映射包含空白或重复 marker: " + object.marker);
			}
			markers.add(object.marker);
			if (object.object_kind === "topic_note") topicNotes++;
			if (object.graph_node_id && !graphIDs.has(object.graph_node_id)) {
				throw new Error("Zotero 映射引用不存在的 graph node: " + object.graph_node_id);
			}
			if (object.parent_graph_node_id && !graphIDs.has(object.parent_graph_node_id)) {
				throw new Error("Zotero 映射引用不存在的 parent graph node: " + object.parent_graph_node_id);
			}
			for (let sourceID of object.linked_source_ids || []) {
				if (!sourceIDs.has(sourceID)) {
					throw new Error("Zotero 映射引用不存在的 source: " + sourceID);
				}
			}
		}
		if (topicNotes !== 1) throw new Error("Zotero 映射必须恰好包含一个 topic_note");
		for (let role of [
				"root", "overview", "knowledge", "research", "sources", "history",
				"research_tensions", "research_frontier", "research_current", "research_claims", "research_reviews",
		]) {
			if (!nativeMap.collections?.[role]) throw new Error("Zotero 映射缺少 Collection role: " + role);
		}
		let accepted = nativeMap.feedback_contract?.accepted_events || [];
		if (!accepted.includes("human_note_modified") || !accepted.includes("human_annotation_modified")) {
			throw new Error("Zotero 映射没有声明完整的 Note/annotation feedback contract");
		}
		if ((nativeMap.feedback_contract?.target_priority || []).join("|") !== "claim|collision_review|research_problem|research_question|real_world_tension|reality_signal_gap|source|knowledge|topic") {
			throw new Error("Zotero 映射缺少 research/source/knowledge/topic fallback feedback priority");
		}
		if (nativeMap.feedback_contract?.lifecycle_effect !== "REVIEW_INPUT_ONLY"
			|| nativeMap.feedback_contract?.history_policy !== "APPEND_ONLY_PRESERVE_OLD_NODES_AND_EDGES") {
			throw new Error("Zotero 映射违反 review-only 或 append-only 历史边界");
		}
		this.workspaceOverride = workspace;
		this.activeWorkspace = workspace;
		this.activeGraph = graph;
		this.activeNativeMap = nativeMap;
		let reviewQueue = await this.readJsonFile(
			PathUtils.join(workspace, "human-input", "review-queue.json"),
			{ schema_version: "0.1", projection: "codex-review-queue", items: [] },
		);
		if (reviewQueue.schema_version !== "0.1" || reviewQueue.projection !== "codex-review-queue"
			|| !Array.isArray(reviewQueue.items)) {
			await this.appendRuntimeStatus("review_queue_invalid", { workspace });
			reviewQueue = { schema_version: "0.1", projection: "codex-review-queue", items: [] };
		}
		this.activeReviewQueue = reviewQueue;
		this.activeRunName = graph.run || run?.key || "ATR Topic";
		this.activeRunRecord = run || null;
		this.activeCollectionID = null;
		this.activeOverviewCollectionID = null;
		this.activeKnowledgeCollectionID = null;
		this.activeResearchCollectionID = null;
		this.activeSourceCollectionID = null;
		this.activeHistoryCollectionID = null;
		await this.appendRuntimeStatus("projection_loaded", {
			run: this.activeRunName,
			node_count: (graph.nodes || []).length,
			edge_count: (graph.edges || []).length,
		});
		await this.appendRuntimeStatus("review_queue_loaded", {
			pending_count: this.pendingReviewItems().length,
		});
		return graph;
	},

	pendingReviewItems(graphNodeID = null, sourceID = null) {
		return (this.activeReviewQueue?.items || []).filter(item => {
			if (!String(item.status || "").startsWith("pending")) return false;
			if (!graphNodeID && !sourceID) return true;
			if (sourceID && item.annotation_source_id === sourceID) return true;
			if (graphNodeID && item.annotation_graph_node_id === graphNodeID) return true;
			return graphNodeID && (item.all_affected_decision_objects || [])
				.some(decision => decision.id === graphNodeID);
		});
	},

	plainNote(html) {
		return String(html || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
	},

	htmlEscape(value) {
		return String(value ?? "").replace(/[&<>"']/g, char => ({
			"&": "&amp;",
			"<": "&lt;",
			">": "&gt;",
			'"': "&quot;",
			"'": "&#39;",
		})[char]);
	},

	topicTitle(graph = this.activeGraph) {
		if (graph === this.activeGraph && this.activeNativeMap?.topic?.title) {
			return this.activeNativeMap.topic.title;
		}
		let nodes = graph?.nodes || [];
		let subject = nodes.find(node => node.kind === "atr_v2_subject" && node.data?.active)
			|| nodes.find(node => node.kind === "atr_v2_subject");
		return subject?.label || graph?.run || this.activeRunName || "ATR Topic";
	},

	async ensureTopicCollection(graph = this.activeGraph) {
		let libraryID = Zotero.Libraries.userLibraryID;
		let name = this.activeNativeMap?.collections?.root || "ATR · " + this.topicTitle(graph);
		let collection = (Zotero.Collections.getByLibrary(libraryID) || [])
			.find(candidate => candidate.name === name);
		if (!collection) {
			collection = new Zotero.Collection();
			collection.libraryID = libraryID;
			collection.name = name;
			await collection.saveTx();
			await this.appendRuntimeStatus("topic_collection_created", {
				collection_id: collection.id,
				collection_name: name,
			});
		}
		this.activeCollectionID = collection.id;
		return collection;
	},

	async ensureChildCollection(parent, name) {
		let libraryID = Zotero.Libraries.userLibraryID;
		let collection = (Zotero.Collections.getByLibrary(libraryID) || [])
			.find(candidate => candidate.parentID === parent.id && candidate.name === name);
		if (!collection) {
			collection = new Zotero.Collection();
			collection.libraryID = libraryID;
			collection.parentID = parent.id;
			collection.name = name;
			await collection.saveTx();
		}
		return collection;
	},

	async ensureTopicCollections(graph = this.activeGraph) {
		let root = await this.ensureTopicCollection(graph);
		let overview = await this.ensureChildCollection(root, this.activeNativeMap?.collections?.overview || "01 · Topic 与演化");
		let knowledge = await this.ensureChildCollection(root, this.activeNativeMap?.collections?.knowledge || "02 · 知识体系");
		let research = await this.ensureChildCollection(root, this.activeNativeMap?.collections?.research || "03 · 研究问题与断言");
		let sources = await this.ensureChildCollection(root, this.activeNativeMap?.collections?.sources || "04 · 来源阅读");
		let history = await this.ensureChildCollection(root, this.activeNativeMap?.collections?.history || "05 · 历史版本");
		let researchTensions = await this.ensureChildCollection(research, this.activeNativeMap?.collections?.research_tensions || "01 · 现实世界张力");
		let researchFrontier = await this.ensureChildCollection(research, this.activeNativeMap?.collections?.research_frontier || "02 · 前沿研究问题");
		let researchCurrent = await this.ensureChildCollection(research, this.activeNativeMap?.collections?.research_current || "03 · 当前问题卡");
		let researchClaims = await this.ensureChildCollection(research, this.activeNativeMap?.collections?.research_claims || "04 · 待审查断言");
		let researchReviews = await this.ensureChildCollection(research, this.activeNativeMap?.collections?.research_reviews || "05 · 共创复核");
		this.activeOverviewCollectionID = overview.id;
		this.activeKnowledgeCollectionID = knowledge.id;
		this.activeResearchCollectionID = research.id;
		this.activeSourceCollectionID = sources.id;
		this.activeHistoryCollectionID = history.id;
		return {
			root, overview, knowledge, research, sources, history,
				researchTensions, researchFrontier, researchCurrent, researchClaims, researchReviews,
		};
	},

	async addToTopicCollection(item, collection) {
		if (!(item.getCollections?.() || []).includes(collection.id)) {
			item.addToCollection(collection.id);
			if (item.isNote?.()) this.suppressedNotifierItemIDs.add(item.id);
			try {
				await item.saveTx();
				await Zotero.Promise.delay(25);
			}
			finally {
				this.suppressedNotifierItemIDs.delete(item.id);
			}
		}
	},

	async searchItems(field, value) {
		if (!value) return [];
		let search = new Zotero.Search();
		search.libraryID = Zotero.Libraries.userLibraryID;
		search.addCondition(field, "is", value);
		let ids = await search.search();
		return ids.length ? await Zotero.Items.getAsync(ids) : [];
	},

	doiFromSource(source) {
		let declared = String(source?.data?.doi || "").trim();
		if (declared) return declared.replace(/^doi:\s*/i, "");
		let match = /^https?:\/\/(?:dx\.)?doi\.org\/(.+)$/i.exec(String(source?.data?.url || "").trim());
		if (!match) return "";
		try {
			return decodeURIComponent(match[1]);
		}
		catch (_) {
			return match[1];
		}
	},

	async findSourceItem(source) {
		let sourceID = source?.data?.source_id;
		let tagged = await this.searchItems("tag", "atr-source-id:" + sourceID);
		let existing = tagged.find(item => item.isRegularItem?.());
		if (existing) return existing;

		let candidates = [];
		let doi = this.doiFromSource(source);
		if (doi) candidates.push(...await this.searchItems("DOI", doi));
		if (source?.data?.url) candidates.push(...await this.searchItems("url", source.data.url));
		if (source?.label) candidates.push(...await this.searchItems("title", source.label));
		existing = candidates.find(item => item.isRegularItem?.());
		if (!existing) return null;

		existing.addTag("ATR");
		existing.addTag("atr-source-id:" + sourceID);
		await existing.saveTx();
		await this.appendRuntimeStatus("source_reused", {
			source_id: sourceID,
			item_key: existing.key,
		});
		return existing;
	},

	async sourceItem(source, collection = null) {
		let sourceID = source?.data?.source_id;
		let item = await this.findSourceItem(source);
		if (!item) {
			let itemType = source?.data?.source_layer === "scholarly_evidence"
				? "journalArticle"
				: "webpage";
			item = new Zotero.Item(itemType);
			item.setField("title", source?.label || sourceID || "ATR source");
			item.setField("url", source?.data?.url || "");
			let doi = this.doiFromSource(source);
			if (itemType === "journalArticle" && doi) {
				item.setField("DOI", doi);
			}
			item.setField("extra", "ATR source ID: " + sourceID);
			item.addTag("ATR");
			item.addTag("atr-source-id:" + sourceID);
			await item.saveTx();
			await this.appendRuntimeStatus("source_stub_created", {
				source_id: sourceID,
				item_key: item.key,
			});
		}
		collection = collection || (await this.ensureTopicCollections()).sources;
		await this.addToTopicCollection(item, collection);
		return item;
	},

	markerFromNote(note) {
		let text = this.plainNote(note?.getNote?.() || "");
		let process = /ATR Process Run:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let knowledge = /ATR Knowledge Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let tension = /ATR Tension Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let realitySignalGap = /ATR Reality Signal Gap:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let researchQuestion = /ATR Research Question Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let derivedQuestion = /ATR Derived Question Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let reviewAssessment = /ATR Review Assessment:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let collisionReview = /ATR Collision Review:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let portfolio = /ATR Portfolio Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let program = /ATR Research Program Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let legacyRun = /ATR Legacy Run Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let alignmentAudit = /ATR Alignment Audit Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		let topicRoute = /ATR Topic Route Node:\s*([^\s<]+)/.exec(text)?.[1] || null;
		return {
			run: /ATR Topic Run:\s*([^\s<]+)/.exec(text)?.[1] || null,
			process,
			source: /ATR Source ID:\s*([^\s<]+)/.exec(text)?.[1] || null,
			claim: /ATR Claim ID:\s*([^\s<]+)/.exec(text)?.[1] || null,
			problem: /ATR Problem ID:\s*([^\s<]+)/.exec(text)?.[1] || null,
			knowledge,
			tension,
			realitySignalGap,
			researchQuestion,
			derivedQuestion,
			reviewAssessment,
			collisionReview,
			portfolio,
			program,
			legacyRun,
			alignmentAudit,
			topicRoute,
			graphNode: /ATR Graph Node:\s*([^\s<]+)/.exec(text)?.[1]
				|| knowledge || tension || researchQuestion || derivedQuestion
				|| collisionReview || realitySignalGap || portfolio || program || legacyRun || alignmentAudit || topicRoute,
		};
	},

	async findMarkedNote(marker) {
		let search = new Zotero.Search();
		search.libraryID = Zotero.Libraries.userLibraryID;
		search.addCondition("note", "contains", marker);
		let ids = await search.search();
		let items = ids.length ? await Zotero.Items.getAsync(ids) : [];
		let expected = {
			run: /ATR Topic Run:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			process: /ATR Process Run:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			source: /ATR Source ID:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			claim: /ATR Claim ID:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			problem: /ATR Problem ID:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			knowledge: /ATR Knowledge Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			tension: /ATR Tension Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			realitySignalGap: /ATR Reality Signal Gap:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			researchQuestion: /ATR Research Question Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
				derivedQuestion: /ATR Derived Question Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			reviewAssessment: /ATR Review Assessment:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			collisionReview: /ATR Collision Review:\s*([^\s<]+)/.exec(marker)?.[1] || null,
				portfolio: /ATR Portfolio Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
				program: /ATR Research Program Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
				legacyRun: /ATR Legacy Run Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
				alignmentAudit: /ATR Alignment Audit Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
			graphNode: /ATR Graph Node:\s*([^\s<]+)/.exec(marker)?.[1] || null,
		};
		return items.find(item => {
			if (!item.isNote?.()) return false;
			let actual = this.markerFromNote(item);
			for (let field of Object.keys(expected)) {
				if (expected[field] && actual[field] !== expected[field]) return false;
			}
			return true;
		}) || null;
	},

	connectedResearchLabels(source) {
		let graph = this.activeGraph || { nodes: [], edges: [] };
		let nodes = graph.nodes || [];
		let edges = graph.edges || [];
		let byID = Object.fromEntries(nodes.map(node => [node.id, node]));
		let labels = [];
		for (let edge of edges) {
			if (edge.source !== source.id && edge.target !== source.id) continue;
			let other = byID[edge.source === source.id ? edge.target : edge.source];
			if (!["real_world_tension", "reality_signal_gap", "research_problem", "research_question", "derived_research_question", "claim", "knowledge_concept"].includes(other?.kind)) continue;
			labels.push(other.label);
		}
		return [...new Set(labels)];
	},

	async ensureTopicNote(graph = this.activeGraph, collection = null) {
		let run = graph?.run || this.activeRunName || "unknown";
		let marker = "ATR Topic Run: " + run;
		let existing = await this.findMarkedNote(marker);
		collection = collection || (await this.ensureTopicCollections(graph)).overview;
		if (existing) {
			await this.addToTopicCollection(existing, collection);
			return existing;
		}

		let nodes = graph?.nodes || [];
		let papers = nodes.filter(node => node.kind === "paper");
		let problems = nodes.filter(node => node.kind === "research_problem");
		let questions = nodes.filter(node => node.kind === "research_question");
		let subject = nodes.find(node => node.kind === "atr_v2_subject" && node.data?.active)
			|| nodes.find(node => node.kind === "atr_v2_subject");
		let note = new Zotero.Item("note");
		let authority = this.activeRunRecord || {};
		note.setNote(
			"<h1>" + this.htmlEscape(this.topicTitle(graph)) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p><strong>ATR state:</strong> " + this.htmlEscape(subject?.data?.state || "未记录") + "</p>"
			+ "<p><strong>视图角色:</strong> " + this.htmlEscape(authority.view_role || "未记录")
			+ " · <strong>控制器:</strong> " + this.htmlEscape(authority.controller_kind || "未记录") + "</p>"
			+ (authority.authority_scope === "NAVIGATION_ONLY"
				? "<p><strong>边界:</strong> 这是历史导航视图，不是 lifecycle authority。</p>"
				: "")
			+ "<h2>当前研究问题</h2>"
			+ (problems.length || questions.length
				? "<ul>" + [...problems, ...questions].map(node => "<li>" + this.htmlEscape(node.label) + "</li>").join("") + "</ul>"
				: "<p>当前投影尚未记录 research problem/question。</p>")
			+ "<h2>来源阅读队列</h2>"
			+ (papers.length
				? "<ul>" + papers.map(node => "<li>" + this.htmlEscape(node.label) + " · " + this.htmlEscape(node.data?.source_id || "无 source id") + "</li>").join("") + "</ul>"
				: "<p>当前投影尚未登记来源。</p>")
			+ "<h2>我的研究笔记</h2>"
			+ "<p>在这里综合跨文献判断；逐篇原文核对请在 Collection 中打开文献，并使用 Reader 标注或来源 review note。</p>"
		);
		note.addToCollection(collection.id);
		await note.saveTx();
		await this.appendRuntimeStatus("topic_note_created", { run, note_key: note.key });
		return note;
	},

	async ensureProcessNote(graph = this.activeGraph, collection = null) {
		let run = graph?.run || this.activeRunName || "unknown";
		let marker = "ATR Process Run: " + run;
		collection = collection || (await this.ensureTopicCollections(graph)).overview;
		let timeline = [...(graph?.timeline || [])]
			.sort((left, right) => String(left.at || "").localeCompare(String(right.at || "")));
		let diagnostics = graph?.diagnostics || [];
		let pendingReviews = this.pendingReviewItems();
		let eventRows = timeline.length
			? "<ol>" + timeline.map(event => {
				let details = [event.kind, event.id, event.review_mode ? "review=" + event.review_mode : null]
					.filter(Boolean).join(" · ");
				let artifacts = (event.artifact_ids || []).join("；");
				return "<li><strong>" + this.htmlEscape(event.at || "未记录时间") + "</strong> · "
					+ this.htmlEscape(event.label || event.kind || event.id || "未命名事件")
					+ (details ? "<br><small>" + this.htmlEscape(details) + "</small>" : "")
					+ (artifacts ? "<br><small>artifact: " + this.htmlEscape(artifacts) + "</small>" : "")
					+ "</li>";
			}).join("") + "</ol>"
			: "<p>当前权威投影没有带时间戳的 ATR event；插件不会补造过程。</p>";
		let diagnosticRows = diagnostics.length
			? "<ul>" + diagnostics.map(item => "<li>" + this.htmlEscape(item) + "</li>").join("") + "</ul>"
			: "<p>当前投影没有结构诊断。</p>";
		let reviewRows = pendingReviews.length
			? "<ul>" + pendingReviews.map(item => {
				let nearest = (item.nearest_decision_objects || []).map(node => node.label).join("；");
					return "<li><strong>" + this.htmlEscape(item.event?.review_stance || item.event?.event || "待审查输入")
						+ "</strong> · target=" + this.htmlEscape(item.review_target_type || "unmapped")
						+ (nearest ? "<br>最近受影响节点：" + this.htmlEscape(nearest) : "")
						+ (item.zotero_open_uri ? "<br><a href=\"" + this.htmlEscape(item.zotero_open_uri) + "\">回到 Zotero 原始高亮</a>" : "")
						+ "<br>边界：仅请求 Codex/owner 审查，不自动改变 lifecycle。</li>";
			}).join("") + "</ul>"
			: "<p>当前没有由 Codex 物化的 pending review queue 项。</p>";
		let generated =
			"<h1>ATR 研究过程 · " + this.htmlEscape(this.topicTitle(graph)) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p><strong>只读边界：</strong>本 Note 由实际落盘的 ATR timeline 生成；它不是人的研究输入，也不会用推测补齐缺失历史。人的综合判断请写入 Topic Note 或具体节点 Note。</p>"
			+ "<h2>实际事件与产物</h2>" + eventRows
			+ "<h2>待审查的人类输入</h2>" + reviewRows
			+ "<h2>当前结构缺口</h2>" + diagnosticRows;
		let note = await this.findMarkedNote(marker);
		if (!note) {
			note = new Zotero.Item("note");
			note.setNote(generated);
			note.addToCollection(collection.id);
			await note.saveTx();
			await this.appendRuntimeStatus("process_note_created", { run, note_key: note.key, event_count: timeline.length });
			return note;
		}
		await this.addToTopicCollection(note, collection);
		if (this.plainNote(note.getNote()) !== this.plainNote(generated)) {
			this.suppressedNotifierItemIDs.add(note.id);
			try {
				note.setNote(generated);
				await note.saveTx();
				await Zotero.Promise.delay(25);
			}
			finally {
				this.suppressedNotifierItemIDs.delete(note.id);
			}
			await this.appendRuntimeStatus("process_note_refreshed", { run, note_key: note.key, event_count: timeline.length });
		}
		return note;
	},

	async ensureProblemNote(problem, projectionObject, collection = null) {
		let problemID = problem?.data?.problem_id;
		if (!problemID) throw new Error("research problem 没有稳定 problem_id");
		let marker = projectionObject?.marker
			|| "ATR Problem ID: " + problemID + " | ATR Graph Node: " + problem.id;
		let existing = await this.findMarkedNote(marker);
		collection = collection || (await this.ensureTopicCollections()).research;
		if (existing) {
			await this.addToTopicCollection(existing, collection);
			return existing;
		}
		let graph = this.activeGraph || { nodes: [], edges: [] };
		let byID = Object.fromEntries((graph.nodes || []).map(node => [node.id, node]));
		let sourceLinkCandidates = (graph.edges || [])
			.filter(edge => edge.source === problem.id || edge.target === problem.id)
			.map(edge => ({ edge, source: byID[edge.source === problem.id ? edge.target : edge.source] }))
			.filter(link => link.source?.kind === "paper");
		let sourceLinkIndex = new Map();
		let roleScore = link => ["problem_posture", "resolves", "leaves_unresolved", "does_not_establish"]
			.filter(field => link.edge?.data?.[field]).length;
		for (let link of sourceLinkCandidates) {
			let previous = sourceLinkIndex.get(link.source.id);
			if (!previous || roleScore(link) > roleScore(previous)) sourceLinkIndex.set(link.source.id, link);
		}
		let sourceLinks = [...sourceLinkIndex.values()];
		let worlds = problem.data?.worlds || problem.data?.counterfactual_worlds || [];
		let note = new Zotero.Item("note");
		let historical = projectionObject?.review_role === "HISTORICAL_VERSION";
		note.setNote(
			"<h1>" + (historical ? "历史问题版本" : "研究问题") + " · " + this.htmlEscape(problem.label) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p>ATR Review Stance: " + (historical ? "HISTORICAL_REFERENCE_ONLY" : "PENDING") + "</p>"
			+ (historical ? "<p><strong>边界：</strong>该 Note 保留已被后续版本替代的历史判断，不是当前 lifecycle target。</p>" : "")
			+ "<h2>竞争世界</h2><ul>"
			+ worlds.map(world => "<li>" + this.htmlEscape(typeof world === "string" ? world : (world.label || "世界") + "：" + (world.explanation || "")) + "</li>").join("")
			+ "</ul><h2>最小判别</h2><p>" + this.htmlEscape(problem.data?.discriminator || problem.data?.smallest_discriminator || "未记录") + "</p>"
			+ "<h2>证伪条件</h2><p>" + this.htmlEscape(problem.data?.falsifier || problem.data?.minimum_falsifier || "未记录") + "</p>"
			+ "<h2>论文在该问题上的作用</h2><ul>" + sourceLinks.map(({ edge, source }) => {
				let role = edge.data || {};
				return "<li><strong>" + this.htmlEscape(source.label) + "</strong> · " + this.htmlEscape(source.data?.source_id || "")
					+ "<br>问题姿态：" + this.htmlEscape(role.problem_posture || "未记录")
					+ "<br>已解决：" + this.htmlEscape(role.resolves || "未记录")
					+ "<br>仍未解决：" + this.htmlEscape(role.leaves_unresolved || "未记录")
					+ "<br>不能推出：" + this.htmlEscape(role.does_not_establish || "未记录") + "</li>";
			}).join("") + "</ul>"
			+ "<h2>我的问题审查</h2><p>这里记录：问题是否值得保留、哪个世界更可信、还缺什么原文或判别证据。</p>"
		);
		note.addToCollection(collection.id);
		await note.saveTx();
		return note;
	},

	async ensureClaimNote(claim, projectionObject, collection = null) {
		let claimID = claim?.data?.claim_id;
		if (!claimID) throw new Error("claim 没有稳定 claim_id");
		let marker = projectionObject?.marker
			|| "ATR Claim ID: " + claimID + " | ATR Graph Node: " + claim.id;
		let existing = await this.findMarkedNote(marker);
		collection = collection || (await this.ensureTopicCollections()).research;
		if (existing) {
			await this.addToTopicCollection(existing, collection);
			return existing;
		}
		let note = new Zotero.Item("note");
		let historical = projectionObject?.review_role === "HISTORICAL_VERSION";
		note.setNote(
			"<h1>" + (historical ? "历史断言版本" : "待审查断言") + " · " + this.htmlEscape(claim.label) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p>ATR Review Stance: " + (historical ? "HISTORICAL_REFERENCE_ONLY" : "PENDING") + "</p>"
			+ (historical ? "<p><strong>边界：</strong>该 Note 只保留历史断言，不是当前 lifecycle target。</p>" : "")
			+ "<p>ATR Source Locator: 请填写支持或反驳该断言的原文定位</p>"
			+ "<h2>适用条件</h2><p>" + this.htmlEscape(JSON.stringify(claim.data?.conditions || {})) + "</p>"
			+ "<h2>禁止外推</h2><p>" + this.htmlEscape((claim.data?.forbidden_claims || []).join("；") || "未记录") + "</p>"
			+ "<h2>我的断言审查</h2><p>这里记录支持、限定、反驳、不确定性或新问题。</p>"
		);
		note.addToCollection(collection.id);
		await note.saveTx();
		return note;
	},

	async ensureReviewAssessmentNote(assessment, projectionObject, collection = null) {
		let marker = projectionObject?.marker
			|| "ATR Review Assessment: " + assessment.data?.assessment_id + " | ATR Graph Node: " + assessment.id;
		let existing = await this.findMarkedNote(marker);
		collection = collection || (await this.ensureTopicCollections()).researchReviews;
		if (existing) {
			await this.addToTopicCollection(existing, collection);
			return existing;
		}
		let data = assessment.data || {};
		let reviewer = data.reviewer || {};
		let evidence = data.evidence_basis || [];
		let impact = data.impact || {};
		let note = new Zotero.Item("note");
		note.setNote(
			"<h1>共创复核 · " + this.htmlEscape(data.outcome || "UNSPECIFIED") + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p><strong>只读边界：</strong>这是已落盘的独立 review artifact。请回到被影响的知识/问题/断言 Note 继续讨论，不要在这里改写复核历史。</p>"
			+ "<h2>复核结论</h2><p>" + this.htmlEscape(data.finding || "未记录") + "</p>"
			+ "<h2>复核者与隔离</h2><p>" + this.htmlEscape(reviewer.id || "未记录")
			+ " · " + this.htmlEscape(reviewer.role || "未记录")
			+ " · 与 disposition owner 隔离=" + this.htmlEscape(String(reviewer.isolated_from_disposition_owner === true)) + "</p>"
			+ "<h2>证据依据及边界</h2><ul>" + evidence.map(row => "<li><strong>"
				+ this.htmlEscape(row.kind || "未记录") + " · " + this.htmlEscape(row.ref || "未记录") + "</strong>"
				+ (row.locator ? "<br>定位：" + this.htmlEscape(row.locator) : "")
				+ "<br>观察：" + this.htmlEscape(row.observation || "未记录")
				+ "<br>不能推出：" + this.htmlEscape(row.does_not_establish || "未记录") + "</li>").join("") + "</ul>"
			+ "<h2>保留的对象</h2><p>" + this.htmlEscape((impact.preserve_object_ids || []).join("；") || "无") + "</p>"
			+ "<h2>需要另写新版本的对象</h2><p>" + this.htmlEscape((impact.reconsider_object_ids || []).join("；") || "无") + "</p>"
			+ "<h2>后续产物</h2><p>" + this.htmlEscape(data.required_followup_artifact_kind || "NONE") + "</p>"
			+ "<h2>控制器边界</h2><p>" + this.htmlEscape(data.controller_boundary || "未记录") + "</p>"
		);
		note.addToCollection(collection.id);
		await note.saveTx();
		return note;
	},

	researchCollectionName(object) {
		let prefix = {
			portfolio_note: "研究组合",
			program_note: "研究计划",
			legacy_run_note: "历史分支",
			alignment_audit_note: "归位审计",
			route_note: "路线草案",
			tension_note: "张力",
			reality_gap_note: "现实证据缺口",
			frontier_question_note: "前沿问题",
			problem_note: "问题卡",
			derived_question_note: "细粒度问题",
			claim_note: "断言",
			review_assessment_note: "共创复核",
			collision_review_note: "碰撞复核",
		}[object.object_kind] || "研究节点";
		let identity = String(object.graph_node_id || object.atr_id).split(":").pop();
		return (prefix + " · " + identity + " · " + object.title).slice(0, 180).trim();
	},

	async ensureResearchNodeNote(node, projectionObject, collection) {
		let marker = projectionObject.marker;
		let existing = await this.findMarkedNote(marker);
		if (existing) {
			await this.addToTopicCollection(existing, collection);
			if (node.kind === "collision_review") await this.ensureOwnerRouteReviewTemplate(existing);
			return existing;
		}
		let linked = (projectionObject.linked_source_ids || [])
			.map(sourceID => this.sourceByID(sourceID)).filter(Boolean);
		let data = node.data || {};
		let title, sections;
		if (node.kind === "real_world_tension") {
			title = "现实世界张力";
			sections = [
				["行动者", data.actor],
				["现行做法", data.incumbent_practice],
				["现实后果", data.material_consequence],
				["候选构念", data.candidate_construct],
				["竞争解释", (data.alternative_explanations || []).join("；")],
				["不能推出", data.does_not_establish],
			];
		}
		else if (node.kind === "reality_signal_gap") {
			title = "现实证据缺口";
			sections = [
				["受限检索结论", data.decision],
				["检索截至", data.searched_through],
				["为什么不能形成张力", data.reason],
				["缺失的来源功能", data.missing_source_function],
				["下一步合法工作", data.next_legal_work],
				["不能推出", data.does_not_establish],
				["控制器边界", data.controller_boundary],
			];
		}
		else if (node.kind === "research_question") {
			title = "前沿研究问题";
			sections = [
				["竞争解释", (data.explanations || []).join("；")],
				["刷新条件", data.freshness],
				["来源属性", data.source],
			];
		}
		else if (node.kind === "collision_review") {
			title = "碰撞复核";
			let comparisons = data.comparisons || {};
			sections = [
				["处置", data.disposition],
				["状态（不是 gate）", data.status],
				["精确碰撞", (comparisons.exact || []).join("；")],
				["断言碰撞", (comparisons.claim || []).join("；")],
				["机制碰撞", (comparisons.mechanism || []).join("；")],
				["组合碰撞", (comparisons.compositional || []).join("；")],
				["相邻工作", (comparisons.adjacent || []).join("；")],
				["残存可检验边界", data.surviving_boundary],
				["覆盖限制", (data.coverage_limits || []).join("；")],
				["竞争解释", (data.alternative_explanations || []).join("；")],
				["下一证据", (data.next_evidence || []).join("；")],
				["不授权", data.does_not_authorize],
			];
		}
		else if (node.kind === "research_portfolio") {
			title = "研究组合";
			sections = [
				["组合边界", data.controller_boundary],
				["说明", "每个 program 是独立 controller authority；组合视图只负责导航。"],
			];
		}
		else if (node.kind === "research_program") {
			title = "研究计划";
			sections = [
				["根问题", data.root_question],
				["当前状态", data.initial_state || data.lifecycle_state],
				["下一步合法工作", data.next_legal_work],
				["碰撞复核处置（不是 gate）", data.posterior_disposition],
				["人的 owner review", data.owner_review_status || "PENDING_HUMAN_OWNER_REVIEW"],
				["残存可检验边界", data.surviving_boundary],
				["下一证据", (data.next_evidence || []).join("；")],
				["控制器边界", data.controller_boundary],
			];
		}
		else if (node.kind === "legacy_research_run") {
			title = "历史研究分支";
			sections = [
				["历史角色", data.catalog_role],
				["旧 catalog disposition", data.catalog_disposition],
				["当前归位", data.alignment_disposition],
				["整合动作", data.integration_action],
				["来源 / claim", String(data.source_count || 0) + " / " + String(data.claim_count || 0)],
				["逐项历史消费映射", data.legacy_mapping_status
					? data.legacy_mapping_status + " · " + String(data.mapped_artifact_count || 0) + " 个 artifact"
					: "尚无逐项 sidecar"],
				["映射用途", (data.mapped_decisions || []).join("；")],
				["映射边界", data.mapping_boundary],
				["成为 current 尚缺", (data.missing_for_current || []).join("；")],
			];
		}
		else if (node.kind === "legacy_mapping_audit") {
			title = "逐项历史消费映射";
			sections = [
				["映射 ID", data.mapping_id],
				["Program", data.program_key || "portfolio"],
				["逐项摘要", JSON.stringify(data.summary || {})],
				["当前 child", data.current_run_id],
				["约束", data.policy],
				["符合性", data.conformance],
			];
		}
		else if (node.kind === "zotero_source_reconciliation") {
			title = "Zotero 本地来源对账";
			sections = [
				["Program", data.program_key || "portfolio"],
				["可用性摘要", JSON.stringify(data.summary || {})],
				["读取策略", JSON.stringify(data.policy || {})],
				["控制器边界", data.controller_boundary],
				["不能推出", "本地书目/PDF 可用不等于全文已检查，也不构成 claim、gate 或 route。"],
			];
		}
		else if (node.kind === "repo_pdf_zotero_handoff_audit") {
			title = "Repo PDF → Zotero 显式导入交接";
			sections = [
				["Program", data.program_key || "portfolio"],
				["交接摘要", JSON.stringify(data.summary || {})],
				["导入策略", JSON.stringify(data.policy || {})],
				["控制器边界", data.controller_boundary],
				["人的动作", "只有点击并打开具体来源时，才会重新核对 digest 后复制为 Zotero stored attachment。"],
			];
		}
		else if (node.kind === "historical_alignment_audit") {
			title = "历史归位审计";
			sections = [
				["审计摘要", JSON.stringify(data.summary || {})],
				["归位结论", data.disposition],
				["来源边界", data.source_boundary],
			];
		}
		else if (node.kind === "topic_route_draft") {
			title = "待独立复核的 Topic Route";
			sections = [
				["候选知识路径", data.selected_track],
				["复核后可能进入", data.next_stage],
				["当前状态", data.review_status],
				["理由", data.rationale],
				["有效期", data.valid_until],
				["不能推出", data.does_not_establish],
			];
		}
		else {
			title = "细粒度研究问题";
			sections = [
				["状态", data.status],
				["最小判别", data.smallest_discriminator],
				["不能推出", data.does_not_establish],
			];
		}
		let note = new Zotero.Item("note");
		note.setNote(
			"<h1>" + title + " · " + this.htmlEscape(node.label) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p>ATR Review Stance: PENDING</p>"
			+ sections.map(([heading, value]) => "<h2>" + this.htmlEscape(heading) + "</h2><p>"
				+ this.htmlEscape(value || "未记录") + "</p>").join("")
			+ "<h2>关联原始来源</h2><ul>"
			+ linked.map(source => "<li>" + this.htmlEscape(source.label) + " · "
				+ this.htmlEscape(source.data?.source_id || "") + "</li>").join("")
			+ "</ul><h2>我的审查与追问</h2>"
			+ "<p>请核对来源、限定当前表述，并记录支持、反驳、不确定性或新的细粒度问题。</p>"
			+ (node.kind === "collision_review" ? this.ownerRouteReviewTemplate() : "")
		);
		note.addToCollection(collection.id);
		await note.saveTx();
		return note;
	},

	ownerRouteReviewTemplate() {
		return "<h2>我的 owner route review</h2>"
			+ "<p><strong>此处是人的明确路线输入，不是 worker 结论，也不会自动推进 lifecycle。</strong></p>"
			+ "<p>ATR Owner Route Input: PENDING</p>"
			+ "<p>ATR Owner Route Rationale: 请先回到关联原文核对，再填写理由</p>"
			+ "<p>可选输入：ACCEPT_REFRAME / REQUEST_MORE_EVIDENCE / PARK_TOPIC / RETIRE_CANDIDATE。</p>";
	},

	async ensureOwnerRouteReviewTemplate(note) {
		if (this.plainNote(note.getNote()).includes("ATR Owner Route Input:")) return note;
		this.suppressedNotifierItemIDs.add(note.id);
		try {
			note.setNote(note.getNote() + this.ownerRouteReviewTemplate());
			await note.saveTx();
			await Zotero.Promise.delay(25);
		}
		finally {
			this.suppressedNotifierItemIDs.delete(note.id);
		}
		await this.appendRuntimeStatus("owner_route_review_template_added", { note_key: note.key });
		return note;
	},

	async ensureResearchProjection(graph, collections, sourceItemsByID) {
		let supportedKinds = new Set([
			"portfolio_note", "program_note", "legacy_run_note", "alignment_audit_note",
			"route_note",
			"tension_note", "reality_gap_note", "frontier_question_note", "problem_note",
			"derived_question_note", "claim_note", "review_assessment_note", "collision_review_note",
		]);
		let objects = (this.activeNativeMap?.objects || [])
			.filter(object => supportedKinds.has(object.object_kind));
		let byGraphID = Object.fromEntries(objects.map(object => [object.graph_node_id, object]));
		let graphNodes = Object.fromEntries((graph.nodes || []).map(node => [node.id, node]));
		let createdCollections = new Map();
		let visiting = new Set();
		let notes = [];
		let ensureObject = async object => {
			if (createdCollections.has(object.graph_node_id)) return createdCollections.get(object.graph_node_id);
			if (visiting.has(object.graph_node_id)) throw new Error("research collection hierarchy contains a cycle: " + object.graph_node_id);
			visiting.add(object.graph_node_id);
			let parent;
			if (object.object_kind === "legacy_run_note" || object.object_kind === "alignment_audit_note"
				|| object.review_role === "HISTORICAL_VERSION") parent = collections.history;
			else if (["portfolio_note", "program_note", "route_note"].includes(object.object_kind)) parent = collections.overview;
			else if (["tension_note", "reality_gap_note"].includes(object.object_kind)) parent = collections.researchTensions;
			else if (object.object_kind === "frontier_question_note") parent = collections.researchFrontier;
			else if (object.object_kind === "claim_note") parent = collections.researchClaims;
			else if (["review_assessment_note", "collision_review_note"].includes(object.object_kind)) parent = collections.researchReviews;
			else parent = collections.researchCurrent;
			if (object.parent_graph_node_id && byGraphID[object.parent_graph_node_id]) {
				parent = await ensureObject(byGraphID[object.parent_graph_node_id]);
			}
			let collection = await this.ensureChildCollection(parent, this.researchCollectionName(object));
			createdCollections.set(object.graph_node_id, collection);
			visiting.delete(object.graph_node_id);
			let node = graphNodes[object.graph_node_id];
			if (node) {
				let note;
				if (object.object_kind === "problem_note") note = await this.ensureProblemNote(node, object, collection);
				else if (object.object_kind === "claim_note") note = await this.ensureClaimNote(node, object, collection);
				else if (object.object_kind === "review_assessment_note") note = await this.ensureReviewAssessmentNote(node, object, collection);
				else note = await this.ensureResearchNodeNote(node, object, collection);
				notes.push(note);
			}
			for (let sourceID of object.linked_source_ids || []) {
				let item = sourceItemsByID.get(sourceID);
				if (item) await this.addToTopicCollection(item, collection);
			}
			return collection;
		};
		for (let object of objects) await ensureObject(object);
		return { collectionCount: createdCollections.size, notes };
	},

	async ensureKnowledgeNote(node, projectionObject, collection) {
		let marker = projectionObject.marker;
		let existing = await this.findMarkedNote(marker);
		if (existing) {
			await this.addToTopicCollection(existing, collection);
			return existing;
		}
		let linked = (projectionObject.linked_source_ids || [])
			.map(sourceID => this.sourceByID(sourceID)).filter(Boolean);
		let note = new Zotero.Item("note");
		let historical = projectionObject?.review_role === "HISTORICAL_VERSION";
		let evidenceSpans = node.data?.evidence_spans || [];
		note.setNote(
			"<h1>" + (historical ? "历史知识版本" : "知识节点") + " · " + this.htmlEscape(node.label) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p>ATR Review Stance: " + (historical ? "HISTORICAL_REFERENCE_ONLY" : "PENDING") + "</p>"
			+ (historical ? "<p><strong>边界：</strong>该 Note 保留被新 artifact 替代的知识图版本，不是当前 review target。</p>" : "")
			+ "<h2>知识核验状态</h2><p>" + this.htmlEscape(node.data?.review_status || "PENDING_SOURCE_REVIEW") + "</p>"
			+ "<h2>定义</h2><p>" + this.htmlEscape(node.data?.definition || "尚未记录可审查定义") + "</p>"
			+ "<h2>原文核验跨度</h2><ul>" + evidenceSpans.map(span => "<li><strong>"
				+ this.htmlEscape((span.source_id || "未记录来源") + " · " + (span.locator || "未记录定位") + " · " + (span.relation || "未记录关系"))
				+ "</strong><br>观察：" + this.htmlEscape(span.observation || "未记录")
				+ "<br>不能推出：" + this.htmlEscape(span.does_not_establish || "未记录") + "</li>").join("") + "</ul>"
			+ "<h2>适用边界</h2><p>" + this.htmlEscape(node.data?.does_not_establish || node.data?.does_not_support || "尚未记录禁止外推边界") + "</p>"
			+ "<h2>关联原始来源</h2><ul>"
			+ linked.map(source => "<li>" + this.htmlEscape(source.label) + " · " + this.htmlEscape(source.data?.source_id || "") + "</li>").join("")
			+ "</ul><h2>我的理解与追问</h2>"
			+ "<p>请用自己的语言重述概念、记录不理解之处，并指出哪一篇原文支持或挑战当前定义。</p>"
		);
		note.addToCollection(collection.id);
		await note.saveTx();
		return note;
	},

	knowledgeCollectionName(object) {
		let identity = String(object.graph_node_id || object.atr_id).split(":").pop();
		return ("知识 · " + identity + " · " + object.title).slice(0, 180).trim();
	},

	async ensureKnowledgeProjection(graph, collections, sourceItemsByID) {
		let objects = (this.activeNativeMap?.objects || []).filter(object => object.object_kind === "knowledge_note");
		let byGraphID = Object.fromEntries(objects.map(object => [object.graph_node_id, object]));
		let graphNodes = Object.fromEntries((graph.nodes || []).map(node => [node.id, node]));
		let createdCollections = new Map();
		let visiting = new Set();
		let notes = [];
		let ensureObject = async object => {
			if (createdCollections.has(object.graph_node_id)) return createdCollections.get(object.graph_node_id);
			if (visiting.has(object.graph_node_id)) throw new Error("knowledge collection hierarchy contains a cycle: " + object.graph_node_id);
			visiting.add(object.graph_node_id);
			let parent = object.review_role === "HISTORICAL_VERSION" ? collections.history : collections.knowledge;
			if (object.parent_graph_node_id && byGraphID[object.parent_graph_node_id]) {
				parent = await ensureObject(byGraphID[object.parent_graph_node_id]);
			}
			let collection = await this.ensureChildCollection(parent, this.knowledgeCollectionName(object));
			createdCollections.set(object.graph_node_id, collection);
			visiting.delete(object.graph_node_id);
			let node = graphNodes[object.graph_node_id];
			if (node) notes.push(await this.ensureKnowledgeNote(node, object, collection));
			for (let sourceID of object.linked_source_ids || []) {
				let item = sourceItemsByID.get(sourceID);
				if (item) await this.addToTopicCollection(item, collection);
			}
			return collection;
		};
		for (let object of objects) await ensureObject(object);
		return { collectionCount: createdCollections.size, notes };
	},

	async ensureSourceReviewNote(source, item = null) {
		let sourceID = source?.data?.source_id;
		let marker = "ATR Source ID: " + sourceID;
		let existing = await this.findMarkedNote(marker);
		if (existing) return existing;
		item = item || await this.sourceItem(source);
		let note = new Zotero.Item("note");
		note.parentItemID = item.id;
		let inspected = (source?.data?.inspection_spans || []).map(span =>
			"<li><strong>" + this.htmlEscape(span.locator || "未记录定位") + "</strong>："
			+ this.htmlEscape(span.observation || "未记录观察") + "</li>"
		).join("");
		note.setNote(
			"<h1>ATR 来源核对 · " + this.htmlEscape(source?.label || sourceID) + "</h1>"
			+ "<p>" + this.htmlEscape(marker) + "</p>"
			+ "<p>ATR Review Stance: PENDING</p>"
			+ "<p>ATR Source Locator: 请填写页码、章节、高亮或段落定位</p>"
			+ "<h2>ATR 当前记录的支持边界</h2><p>" + this.htmlEscape(source?.data?.supports || "未记录") + "</p>"
			+ "<h2>不能由该来源推出</h2><p>" + this.htmlEscape(source?.data?.does_not_support || source?.data?.does_not_establish || "未记录") + "</p>"
			+ "<h2>ATR 已检查的原文跨度</h2>" + (inspected ? "<ul>" + inspected + "</ul>" : "<p>尚无已落盘的原文检查跨度。</p>")
			+ "<p><strong>Zotero 边界：</strong>" + this.htmlEscape(source?.data?.zotero_attachment_state || "未记录附件状态")
			+ "；快照：" + this.htmlEscape(source?.data?.zotero_snapshot_state || "未记录") + "。</p>"
			+ "<h2>我的原文核对</h2><p>请写下摘录、定位、限定条件、反例或新问题。</p>"
		);
		await note.saveTx();
		await this.appendRuntimeStatus("source_review_note_created", {
			source_id: sourceID,
			note_key: note.key,
		});
		return note;
	},

	async openNativeNote(note) {
		let editor = await Zotero.Notes.open(note.id, null, {
			openInWindow: false,
			allowDuplicate: false,
		});
		await this.appendRuntimeStatus("native_note_tab_opened", {
			note_key: note.key,
		});
		return editor;
	},

	unregisterReadingNoteSection() {
		if (!this.readingNoteSectionID) return;
		Zotero.ItemPaneManager.unregisterSection(this.readingNoteSectionID);
		this.readingNoteSectionID = null;
		this.readingNoteID = null;
		this.readingContextItemID = null;
	},

	async registerReadingNoteSection(note, contextItem, focusNode = this.companionFocusNode) {
		contextItem = this.regularItemFromContext(contextItem);
		if (!contextItem) throw new Error("当前 Reader 没有可绑定的 Zotero 文献条目");
		if (this.readingNoteSectionID
			&& this.readingNoteID === note.id
			&& this.readingContextItemID === contextItem.id) {
			return this.readingNoteSectionID;
		}
		this.unregisterReadingNoteSection();
		this.readingNoteID = note.id;
		this.readingContextItemID = contextItem.id;
		let paneID = "atr-reading-note-" + note.key.toLowerCase();
		let sectionID = Zotero.ItemPaneManager.registerSection({
			paneID,
			pluginID: this.id,
			header: {
				l10nID: "atr-reading-note-header",
				icon: "chrome://zotero/skin/16/universal/note.svg",
			},
			sidenav: {
				l10nID: "atr-reading-note-sidenav",
				icon: "chrome://zotero/skin/20/universal/note.svg",
			},
			bodyXHTML: `
<html:style>
  .atr-reading-note-shell { display: grid; gap: 8px; }
  .atr-reading-note-editor { display: block; min-height: 220px; height: 32vh; max-height: 420px; }
  .atr-reading-visual-context { border-top: 1px solid var(--fill-quinary, #d9e2ec); padding-top: 4px; }
</html:style>
<html:div class="atr-reading-note-shell">
  <note-editor class="atr-reading-note-editor"></note-editor>
  <html:div class="atr-reading-visual-context"></html:div>
</html:div>`,
			sectionButtons: [{
				type: "openNoteTab",
				icon: "chrome://zotero/skin/16/universal/open-link.svg",
				l10nID: "atr-reading-note-open-tab",
				onClick: () => this.openNativeNote(note),
			}, {
				type: "closeReadingNote",
				icon: "chrome://zotero/skin/16/universal/minus.svg",
				l10nID: "atr-reading-note-close",
				onClick: () => this.unregisterReadingNoteSection(),
			}],
			onItemChange: ({ item, setEnabled }) => {
				let selected = this.regularItemFromContext(item);
				setEnabled(selected?.id === contextItem.id);
				return true;
			},
			onRender: ({ setSectionSummary }) => {
				setSectionSummary(note.getNoteTitle?.() || "我的原文核对");
			},
			onAsyncRender: async ({ body }) => {
				let editorElement = body.querySelector("note-editor");
				if (!editorElement) throw new Error("Zotero 没有创建原生 note-editor");
				for (let attempt = 0; attempt < 100 && !editorElement._initialized; attempt++) {
					await Zotero.Promise.delay(25);
				}
				if (!editorElement._initialized) throw new Error("原生 note-editor 初始化超时");
				editorElement.mode = "edit";
				editorElement.viewMode = "library";
				editorElement.parent = note.parentItem;
				editorElement.item = note;
				for (let attempt = 0; attempt < 100 && !editorElement._editorInstance; attempt++) {
					await Zotero.Promise.delay(25);
				}
				await editorElement._editorInstance?._initPromise;
				let visualContext = body.querySelector(".atr-reading-visual-context");
				if (!visualContext) throw new Error("共读 section 缺少可视化上下文容器");
				visualContext.replaceChildren();
				this.appendReadingVisualContext(body.ownerDocument, visualContext, focusNode, contextItem);
			},
		});
		if (!sectionID) throw new Error("Zotero 未能注册阅读笔记 section");
		this.readingNoteSectionID = sectionID;
		await this.appendRuntimeStatus("native_reader_note_section_registered", {
			note_key: note.key,
			context_item_key: contextItem.key,
			pane_id: sectionID,
			interaction: "READER_ITEM_PANE_NATIVE_NOTE_EDITOR",
		});
		return sectionID;
	},

	async openNoteBesideReader(note) {
		let win = Zotero.getMainWindow();
		let tabID = win?.Zotero_Tabs?.selectedID;
		let reader = tabID ? Zotero.Reader.getByTabID(tabID) : null;
		let contextPane = win?.ZoteroContextPane;
		let context = contextPane?.context;
		if (!reader || !context) {
			return this.openNativeNote(note);
		}

		try {
			// Keep Zotero's Reader in item-details mode so the editable human Note
			// and the ATR context section can coexist as two native disclosures.
			// This follows the same official ItemPaneManager + native note-editor
			// pattern used by mature Zotero note plugins.
			let attachment = Zotero.Items.get(reader.itemID);
			let contextItem = this.regularItemFromContext(attachment)
				|| this.regularItemFromContext(note.parentItem);
			let sectionID = await this.registerReadingNoteSection(note, contextItem, this.companionFocusNode);
			contextPane.collapsed = false;
			context.mode = "item";
			await Zotero.Promise.delay(50);
			let itemContext = context._getItemContext?.(tabID);
			itemContext?.scrollToPane?.(sectionID);
			await this.appendRuntimeStatus("native_reader_note_section_ready", {
				note_key: note.key,
				reader_attachment_id: reader.itemID,
				pane_id: sectionID,
				atr_pane_id: this.sectionID,
				interaction: "READER_WITH_FOLDABLE_NOTE_AND_ATR_SECTIONS",
			});
			return sectionID;
		}
		catch (error) {
			await this.appendRuntimeStatus("native_reader_note_section_fallback", {
				note_key: note.key,
				error: String(error),
			});
			return this.openNativeNote(note);
		}
	},

	regularItemFromContext(item) {
		let current = item;
		if (current?.isAnnotation?.()) current = Zotero.Items.get(current.parentItemID);
		if (current?.isNote?.() && current.parentItemID) current = Zotero.Items.get(current.parentItemID);
		if (current?.isAttachment?.() && current.parentItemID) current = Zotero.Items.get(current.parentItemID);
		return current?.isRegularItem?.() ? current : null;
	},

	async coReadingNote(focusNode, item) {
		if (item?.isNote?.() && this.hasATRContext(item)) return item;
		if (focusNode?.kind === "paper") {
			return this.ensureSourceReviewNote(focusNode, this.regularItemFromContext(item));
		}
		let object = (this.activeNativeMap?.objects || [])
			.find(candidate => candidate.graph_node_id === focusNode?.id);
		if (object?.marker) {
			let note = await this.findMarkedNote(object.marker);
			if (note) return note;
		}
		return this.ensureTopicNote();
	},

	companionWindowAlive() {
		return !!(this.companionWindow && !this.companionWindow.closed
			&& !Components.utils.isDeadWrapper(this.companionWindow));
	},

	async openCompanionWindow(focusNode = this.companionFocusNode, item = this.companionItem) {
		this.companionFocusNode = focusNode || null;
		this.companionItem = item || null;
		if (this.companionWindowAlive()) {
			await this.renderCompanionWindow();
			this.companionWindow.focus();
			return this.companionWindow;
		}
		let keepTop = Zotero.Prefs.get("extensions.atr-zotero-workbench.companion.keepTop", true) !== false;
		let features = "chrome,extrachrome,resizable=yes,scrollbars,status,dialog=no,width=460,height=760"
			+ (keepTop ? ",alwaysRaised=yes" : "");
		let win = Zotero.getMainWindow().openDialog(
			"chrome://atr-zotero-workbench/content/companion.xhtml",
			"atr-zotero-companion",
			features,
			{},
		);
		if (!win) throw new Error("Zotero 没有创建 ATR 共读伴随窗");
		this.companionWindow = win;
		for (let attempt = 0; attempt < 100 && !win.document.getElementById("atr-companion-root"); attempt++) {
			await Zotero.Promise.delay(25);
		}
		if (!win.document.getElementById("atr-companion-root")) {
			win.close();
			throw new Error("ATR 共读伴随窗未能加载其文档根节点");
		}
		// openDialog first unloads its transient about:blank document while
		// navigating to the registered chrome URL. Register close cleanup only
		// after the real companion document exists, or that navigation would
		// incorrectly clear the live window reference.
		win.addEventListener("unload", () => {
			if (this.companionWindow === win) this.companionWindow = null;
		}, { once: true });
		await this.renderCompanionWindow();
		await this.appendRuntimeStatus("co_reading_companion_opened", {
			focus_node_id: this.companionFocusNode?.id || null,
			keep_top: keepTop,
			interaction: "PDF_NATIVE_NOTE_AND_PORTABLE_ATR_CONTEXT",
		});
		return win;
	},

	async reopenCompanionWindowWithTopMode(keepTop) {
		Zotero.Prefs.set("extensions.atr-zotero-workbench.companion.keepTop", keepTop, true);
		if (this.companionWindowAlive()) this.companionWindow.close();
		this.companionWindow = null;
		return this.openCompanionWindow();
	},

	async renderCompanionWindow() {
		if (!this.companionWindowAlive()) return;
		let win = this.companionWindow;
		let doc = win.document;
		let root = doc.getElementById("atr-companion-root");
		if (!root) return;
		root.replaceChildren();
		doc.title = "ATR 共读伴随窗 · " + this.topicTitle();
		let toolbar = this.htmlElement(doc, "div");
		toolbar.className = "atr-companion-toolbar";
		let keepTop = Zotero.Prefs.get("extensions.atr-zotero-workbench.companion.keepTop", true) !== false;
		this.appendPaneButton(doc, toolbar, keepTop ? "取消置顶" : "保持置顶", () => {
			return this.reopenCompanionWindowWithTopMode(!keepTop);
		});
		this.appendPaneButton(doc, toolbar, "全部折叠", () => {
			for (let details of root.querySelectorAll("details[data-atr-dock-key]")) details.open = false;
		});
		this.appendPaneButton(doc, toolbar, "只看问题", () => {
			for (let details of root.querySelectorAll("details[data-atr-dock-key]")) {
				details.open = details.dataset.atrDockKey === "problem";
			}
		});
		root.append(toolbar);
		let content = this.htmlElement(doc, "main");
		content.className = "atr-companion-content";
		this.appendCoReadingDock(doc, content, this.companionFocusNode, this.companionItem, true);
		root.append(content);
	},

	async openThreePaneCoReading(focusNode, item) {
		let note = await this.coReadingNote(focusNode, item);
		await this.openNoteBesideReader(note);
		await this.openCompanionWindow(focusNode, item);
		await this.appendRuntimeStatus("three_surface_coreading_ready", {
			focus_node_id: focusNode?.id || null,
			note_key: note.key,
			surfaces: ["ZOTERO_READER", "ZOTERO_NATIVE_NOTE_EDITOR", "ATR_PORTABLE_CONTEXT"],
		});
		return note;
	},

	async openCurrentReadingNote(item = this.companionItem) {
		let note = await this.coReadingNote(this.companionFocusNode, item);
		return this.openNoteBesideReader(note);
	},

	async ensureReadableAttachment(source, item) {
		if (item.isAttachment?.()) return item;
		let existing = await item.getBestAttachment();
		if (existing) {
			await this.appendRuntimeStatus("source_fulltext_ready", {
				source_id: source?.data?.source_id,
				item_key: item.key,
				attachment_key: existing.key,
				access_route: "EXISTING_ZOTERO_ATTACHMENT",
				fulltext_state: "FULLTEXT_ATTACHED",
			});
			return existing;
		}
		let nativeSource = (this.activeNativeMap?.objects || []).find(object =>
			object.object_kind === "source_item" && object.atr_id === source?.data?.source_id
		);
		let localPDFPath = nativeSource?.local_cache_import_state === "READY"
			? nativeSource.verified_local_pdf_path : null;
		let pdfURL = source?.data?.pdf_url;
		if (pdfURL && !/^https:\/\/[^\s]+$/i.test(pdfURL)) {
			throw new Error("来源的开放 PDF URL 不是受支持的 HTTPS 地址。");
		}
		let importKey = item.libraryID + ":" + item.key;
		if (!this.pendingSourceImports.has(importKey)) {
			let pending = (async () => {
				if (localPDFPath) {
					await this.appendRuntimeStatus("source_local_pdf_import_started", {
						source_id: source?.data?.source_id,
						item_key: item.key,
						local_cache_path: source?.data?.local_cache_path,
					});
					let expectedDigest = String(source?.data?.content_digest || nativeSource?.content_digest || "");
					let actualDigest = await this.sha256File(localPDFPath);
					if (expectedDigest !== "sha256:" + actualDigest) {
						await this.appendRuntimeStatus("source_local_pdf_digest_mismatch", {
							source_id: source?.data?.source_id,
							expected_digest: expectedDigest,
							actual_digest: "sha256:" + actualDigest,
						});
						throw new Error("身份已核验的本地 PDF 在投影后发生变化，已拒绝导入 Zotero。");
					}
					let attachment = await Zotero.Attachments.importFromFile({
						file: localPDFPath,
						libraryID: item.libraryID,
						parentItemID: item.id,
						title: "Verified full text",
					});
					await this.appendRuntimeStatus("source_local_pdf_imported", {
						source_id: source?.data?.source_id,
						item_key: item.key,
						attachment_key: attachment.key,
						access_route: "VERIFIED_REPO_CACHE_TO_ZOTERO_STORED_COPY",
						fulltext_state: "FULLTEXT_ATTACHED",
					});
					return attachment;
				}
				if (pdfURL) {
					await this.appendRuntimeStatus("source_pdf_import_started", {
						source_id: source?.data?.source_id,
						item_key: item.key,
						pdf_url: pdfURL,
					});
					try {
						let attachment = await Zotero.Attachments.importFromURL({
							libraryID: item.libraryID,
							url: pdfURL,
							parentItemID: item.id,
							title: "Open-access full text",
							contentType: "application/pdf",
							renameIfAllowedType: true,
						});
						await this.appendRuntimeStatus("source_pdf_imported", {
							source_id: source?.data?.source_id,
							item_key: item.key,
							attachment_key: attachment.key,
							access_route: "EXPLICIT_OPEN_PDF_URL",
							fulltext_state: "FULLTEXT_ATTACHED",
						});
						return attachment;
					}
					catch (error) {
						await this.appendRuntimeStatus("source_pdf_import_failed", {
							source_id: source?.data?.source_id,
							item_key: item.key,
							error: String(error),
						});
						throw error;
					}
				}

				if (!Zotero.Attachments.canFindFileForItem(item)) {
					await this.appendRuntimeStatus("source_available_file_not_eligible", {
						source_id: source?.data?.source_id,
						item_key: item.key,
						fulltext_state: "METADATA_ONLY",
					});
					return null;
				}
				await this.appendRuntimeStatus("source_available_file_lookup_started", {
					source_id: source?.data?.source_id,
					item_key: item.key,
					doi: this.doiFromSource(source) || null,
					access_route: "ZOTERO_NATIVE_AVAILABLE_FILE",
				});
				let attachment;
				try {
					attachment = await Zotero.Attachments.addAvailableFile(item);
				}
				catch (error) {
					await this.appendRuntimeStatus("source_available_file_lookup_failed", {
						source_id: source?.data?.source_id,
						item_key: item.key,
						fulltext_state: "ACCESS_REQUIRED",
						error: String(error),
					});
					throw error;
				}
				if (!attachment) {
					await this.appendRuntimeStatus("source_available_file_not_found", {
						source_id: source?.data?.source_id,
						item_key: item.key,
						fulltext_state: "ACCESS_REQUIRED",
					});
					return null;
				}
				await this.appendRuntimeStatus("source_available_file_attached", {
					source_id: source?.data?.source_id,
					item_key: item.key,
					attachment_key: attachment.key,
					access_route: "ZOTERO_NATIVE_AVAILABLE_FILE",
					fulltext_state: "FULLTEXT_ATTACHED",
				});
				return attachment;
			})();
			this.pendingSourceImports.set(importKey, pending);
		}
		try {
			return await this.pendingSourceImports.get(importKey);
		}
		finally {
			this.pendingSourceImports.delete(importKey);
		}
	},

	async openSourceInReader(source, item = null) {
		item = item || await this.sourceItem(source);
		let annotation = item.isAnnotation?.() ? item : null;
		let attachment = annotation
			? Zotero.Items.get(annotation.parentItemID)
			: await this.ensureReadableAttachment(source, item);
		if (!attachment) {
			throw new Error("Zotero 没有找到当前访问条件下可用的全文。该条目仍只是书目记录；请通过机构访问、开放仓储/作者稿，或把你已有的 PDF 添加为附件后再阅读。");
		}
		let location = annotation ? { annotationID: annotation.key } : null;
		await Zotero.Reader.open(attachment.id, location, {
			openInWindow: false,
			allowDuplicate: false,
		});
		await this.appendRuntimeStatus("native_reader_tab_opened", {
			source_id: source?.data?.source_id,
			item_key: item.key,
			attachment_key: attachment.key,
			annotation_key: annotation?.key || null,
		});
		if (annotation) {
			await this.appendRuntimeStatus("native_reader_annotation_opened", {
				source_id: source?.data?.source_id,
				attachment_key: attachment.key,
				annotation_key: annotation.key,
			});
		}
		return attachment;
	},

	async openSourceForCoReading(source, item = null, withPortableContext = false) {
		item = item || await this.sourceItem(source);
		let sourceItem = this.regularItemFromContext(item) || item;
		this.companionFocusNode = source;
		this.companionItem = item;
		await this.openSourceInReader(source, item);
		// Let Zotero finish selecting the Reader tab before switching its
		// context pane into the native note-editor mode.
		await Zotero.Promise.delay(100);
		let note = await this.ensureSourceReviewNote(source, sourceItem);
		await this.openNoteBesideReader(note);
		if (withPortableContext) await this.openCompanionWindow(source, item);
		await this.appendRuntimeStatus("source_coreading_opened", {
			source_id: source?.data?.source_id,
			note_key: note.key,
			portable_context: withPortableContext,
			interaction: "ZOTERO_READER_WITH_NATIVE_SOURCE_NOTE",
		});
		return note;
	},

	async sha256File(path) {
		let bytes = await IOUtils.read(path);
		let hasher = Cc["@mozilla.org/security/hash;1"].createInstance(Ci.nsICryptoHash);
		hasher.init(hasher.SHA256);
		hasher.update(bytes, bytes.length);
		return Array.from(hasher.finish(false), char => char.charCodeAt(0).toString(16).padStart(2, "0")).join("");
	},

	async syncTopic(graph = this.activeGraph) {
		let collections = await this.ensureTopicCollections(graph);
		let collection = collections.root;
		let note = await this.ensureTopicNote(graph, collections.overview);
		let processNote = await this.ensureProcessNote(graph, collections.overview);
		await this.addToTopicCollection(note, collection);
		await this.addToTopicCollection(processNote, collection);
		let byID = Object.fromEntries((graph?.nodes || []).map(node => [node.id, node]));
		let sources = (this.activeNativeMap?.objects || [])
			.filter(object => object.object_kind === "source_item")
			.map(object => byID[object.graph_node_id])
			.filter(Boolean);
		let items = [];
		let sourceItemsByID = new Map();
		for (let source of sources) {
			let item = await this.sourceItem(source, collections.sources);
			items.push(item);
			sourceItemsByID.set(source.data?.source_id, item);
		}
		let knowledge = await this.ensureKnowledgeProjection(graph, collections, sourceItemsByID);
		let research = await this.ensureResearchProjection(graph, collections, sourceItemsByID);
		await this.appendRuntimeStatus("native_topic_synced", {
			collection_id: collection.id,
			note_key: note.key,
			process_note_key: processNote.key,
			source_count: items.length,
			research_collection_count: research.collectionCount,
			research_note_count: research.notes.length,
			knowledge_collection_count: knowledge.collectionCount,
			knowledge_note_count: knowledge.notes.length,
		});
		return {
			collection, note, processNote, sources, items,
			decisionNotes: research.notes,
			researchNotes: research.notes,
			knowledgeNotes: knowledge.notes,
			collections,
		};
	},

	async openTopic(run, window) {
		try {
			let graph = await this.loadProjection(run || await this.defaultRun());
			let synced = await this.syncTopic(graph);
			let { collection, note } = synced;
			window.Zotero_Tabs.select("zotero-pane");
			await window.ZoteroPane.collectionsView.selectCollection(collection.id);
			await this.openNativeNote(note);
			return synced;
		}
		catch (error) {
			this.log("could not open native topic: " + error);
			await this.appendRuntimeStatus("native_topic_open_failed", { error: String(error) });
			Services.prompt.alert(window, "ATR Research", "无法打开 ATR Topic：\n" + error);
		}
	},

	sourceIDFromItem(item) {
		if (!item) return null;
		let current = item;
		if (current.isAnnotation?.()) current = Zotero.Items.get(current.parentItemID);
		if (current?.isAttachment?.() && current.parentItemID) current = Zotero.Items.get(current.parentItemID);
		if (current?.isNote?.() && current.parentItemID) current = Zotero.Items.get(current.parentItemID);
		let tag = (current?.getTags?.() || []).map(entry => entry.tag)
			.find(value => value.startsWith("atr-source-id:"));
		if (tag) return tag.slice("atr-source-id:".length);
		return /ATR source ID:\s*([^\s]+)/.exec(current?.getField?.("extra") || "")?.[1] || null;
	},

	sourceByID(sourceID) {
		return (this.activeGraph?.nodes || [])
			.find(node => node.kind === "paper" && node.data?.source_id === sourceID) || null;
	},

	hasATRContext(item) {
		if (!item) return false;
		if (this.sourceIDFromItem(item)) return true;
		if (item.isNote?.()) {
			let marker = this.markerFromNote(item);
			return !!(marker.run || marker.process || marker.source || marker.claim || marker.problem || marker.knowledge
				|| marker.tension || marker.realitySignalGap || marker.researchQuestion || marker.derivedQuestion || marker.portfolio
				|| marker.program || marker.legacyRun || marker.alignmentAudit || marker.topicRoute || marker.collisionReview);
		}
		return false;
	},

	htmlElement(doc, name, text = null) {
		let element = doc.createElementNS("http://www.w3.org/1999/xhtml", name);
		if (text !== null) element.textContent = text;
		return element;
	},

	appendPaneText(doc, body, text, strong = false) {
		let paragraph = this.htmlElement(doc, "p", text);
		paragraph.style.margin = "6px 0";
		paragraph.style.whiteSpace = "normal";
		if (strong) paragraph.style.fontWeight = "600";
		body.append(paragraph);
		return paragraph;
	},

	appendPaneButton(doc, body, label, callback, primary = false) {
		let button = this.htmlElement(doc, "button", label);
		button.type = "button";
		button.style.margin = "4px 6px 4px 0";
		button.style.padding = "5px 9px";
		if (primary) button.style.fontWeight = "600";
		button.addEventListener("click", async () => {
			button.disabled = true;
			try {
				await callback();
			}
			catch (error) {
				Services.prompt.alert(doc.defaultView, "ATR Research", String(error));
			}
			finally {
				button.disabled = false;
			}
		});
		body.append(button);
		return button;
	},

	async setReviewStance(note, stance) {
		let html = note.getNote();
		let line = "ATR Review Stance: " + stance;
		if (/ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING|HISTORICAL_REFERENCE_ONLY)/.test(html)) {
			html = html.replace(
				/ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING|HISTORICAL_REFERENCE_ONLY)/,
				line,
			);
		}
		else {
			html = "<p>" + line + "</p>" + html;
		}
		note.setNote(html);
		await note.saveTx();
		await Zotero.Promise.delay(50);
		await this.appendRuntimeStatus("human_review_stance_selected", {
			note_key: note.key,
			stance,
		});
		return note;
	},

	appendReviewStanceButtons(doc, body, noteProvider) {
		let details = this.htmlElement(doc, "details");
		details.style.borderTop = "1px solid var(--fill-quinary, #d9e2ec)";
		details.style.marginTop = "8px";
		details.style.padding = "6px 0";
		let summary = this.htmlElement(doc, "summary", "记录我的判断（进入待复审队列）");
		summary.style.cursor = "pointer";
		summary.style.fontWeight = "600";
		details.append(summary);
		let controls = this.htmlElement(doc, "div");
		controls.style.padding = "6px 2px 0 10px";
		details.append(controls);
		for (let [label, stance] of [
			["支持", "SUPPORTS"],
			["需要限定", "QUALIFIES"],
			["反驳", "CHALLENGES"],
			["尚不能判断", "UNSURE"],
			["提出新问题", "NEW_QUESTION"],
		]) {
			this.appendPaneButton(doc, controls, label, async () => {
				let note = await noteProvider();
				await this.setReviewStance(note, stance);
				await this.openNativeNote(note);
			});
		}
		body.append(details);
	},

	async setOwnerRouteInput(note, disposition, rationale) {
		let html = note.getNote();
		let inputLine = "ATR Owner Route Input: " + disposition;
		let rationaleLine = "ATR Owner Route Rationale: " + this.htmlEscape(rationale.trim());
		if (/ATR Owner Route Input:\s*(PENDING|ACCEPT_REFRAME|REQUEST_MORE_EVIDENCE|PARK_TOPIC|RETIRE_CANDIDATE)/.test(html)) {
			html = html.replace(
				/ATR Owner Route Input:\s*(PENDING|ACCEPT_REFRAME|REQUEST_MORE_EVIDENCE|PARK_TOPIC|RETIRE_CANDIDATE)/,
				inputLine,
			);
		}
		else html += "<p>" + inputLine + "</p>";
		if (/ATR Owner Route Rationale:\s*[^<]*/.test(html)) {
			html = html.replace(/ATR Owner Route Rationale:\s*[^<]*/, rationaleLine);
		}
		else html += "<p>" + rationaleLine + "</p>";
		note.setNote(html);
		await note.saveTx();
		await Zotero.Promise.delay(50);
		await this.appendRuntimeStatus("human_owner_route_input_selected", {
			note_key: note.key,
			disposition,
			lifecycle_effect: "REVIEW_INPUT_ONLY",
		});
		return note;
	},

	appendOwnerRouteReviewControls(doc, body, noteProvider) {
		let details = this.htmlElement(doc, "details");
		details.style.borderTop = "1px solid var(--fill-quinary, #d9e2ec)";
		details.style.marginTop = "8px";
		details.style.padding = "6px 0";
		let summary = this.htmlElement(doc, "summary", "完成我的 owner route review");
		summary.style.cursor = "pointer";
		summary.style.fontWeight = "600";
		details.append(summary);
		let controls = this.htmlElement(doc, "div");
		controls.style.padding = "6px 2px 0 10px";
		details.append(controls);
		this.appendPaneText(doc, controls, "必须给出理由；输入进入 Codex 待复审队列，但不会自动改变 gate、route 或历史。", true);
		for (let [label, disposition] of [
			["接受收窄边界", "ACCEPT_REFRAME"],
			["要求补充证据", "REQUEST_MORE_EVIDENCE"],
			["暂时停放 topic", "PARK_TOPIC"],
			["清退候选问题", "RETIRE_CANDIDATE"],
		]) {
			this.appendPaneButton(doc, controls, label, async () => {
				let input = { value: "" };
				let accepted = Services.prompt.prompt(
					doc.defaultView,
					"ATR owner route review",
					"请写明依据、仍不确定的地方，以及你实际核对过的原文：",
					input,
					null,
					{},
				);
				if (!accepted) return;
				if (!input.value.trim()) throw new Error("owner route review 必须包含非空理由。");
				let note = await noteProvider();
				await this.setOwnerRouteInput(note, disposition, input.value);
				await this.openNativeNote(note);
			});
		}
		body.append(details);
	},

	appendPendingReviewSummary(doc, body, graphNodeID = null, sourceID = null) {
		let items = this.pendingReviewItems(graphNodeID, sourceID);
		if (!items.length) return;
		this.appendPaneText(doc, body, "待 Codex/owner 审查的人类输入：" + items.length, true);
		let nearest = [...new Set(items.flatMap(item =>
			(item.nearest_decision_objects || []).map(node => node.label)
		))].slice(0, 3);
		if (nearest.length) this.appendPaneText(doc, body, "最近受影响节点：" + nearest.join("；"));
		this.appendPaneText(doc, body, "这些输入尚未改变 ATR lifecycle 或历史路线。");
	},

	dockPreference(key, fallback) {
		let value = Zotero.Prefs.get("extensions.atr-zotero-workbench.dock." + key, true);
		return typeof value === "boolean" ? value : fallback;
	},

	nearestGraphNodes(startID, kinds, limit = 5, maxDepth = 3) {
		if (!startID) return [];
		let graph = this.activeGraph || { nodes: [], edges: [] };
		let byID = Object.fromEntries((graph.nodes || []).map(node => [node.id, node]));
		let adjacency = new Map();
		for (let edge of graph.edges || []) {
			if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
			if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
			adjacency.get(edge.source).push(edge.target); adjacency.get(edge.target).push(edge.source);
		}
		let queue = [[startID, 0]], visited = new Set([startID]), found = [];
		while (queue.length && found.length < limit) {
			let [current, depth] = queue.shift(); let node = byID[current];
			if (current !== startID && node && kinds.has(node.kind)) found.push(node);
			if (depth >= maxDepth) continue;
			for (let next of adjacency.get(current) || []) if (!visited.has(next)) {
				visited.add(next); queue.push([next, depth + 1]);
			}
		}
		return found;
	},

	appendDockDisclosure(doc, parent, key, title, rows, fallbackOpen, showEmpty = true) {
		let details = this.htmlElement(doc, "details");
		details.dataset.atrDockKey = key;
		details.open = this.dockPreference(key + "Open", fallbackOpen);
		details.style.borderTop = "1px solid var(--fill-quinary, #d9e2ec)";
		details.style.padding = "6px 0";
		let summary = this.htmlElement(doc, "summary", title + (rows.length ? " · " + rows.length : ""));
		summary.style.cursor = "pointer"; summary.style.fontWeight = "600"; details.append(summary);
		let content = this.htmlElement(doc, "div"); content.style.padding = "4px 2px 2px 10px"; details.append(content);
		for (let row of rows) {
			let line = this.htmlElement(doc, "button", row.label);
			line.type = "button"; line.style.display = "block"; line.style.width = "100%";
			line.style.textAlign = "left"; line.style.margin = "3px 0"; line.style.padding = "4px 6px";
			line.style.border = "0"; line.style.borderRadius = "5px"; line.style.background = "transparent";
			if (row.onClick) line.addEventListener("click", row.onClick);
			content.append(line);
		}
		if (!rows.length && key !== "detail" && showEmpty) this.appendPaneText(doc, content, "当前对象附近尚无已落盘节点；不会补造连接。");
		details.addEventListener("toggle", () => Zotero.Prefs.set(
			"extensions.atr-zotero-workbench.dock." + key + "Open", details.open, true,
		));
		parent.append(details);
		return content;
	},

	appendMiniGraph(doc, parent, focusNode, relatedNodes, openNode) {
		if (!focusNode) {
			this.appendPaneText(doc, parent, "当前对象附近尚无已落盘节点；不会补造连接。");
			return null;
		}
		let svgNS = "http://www.w3.org/2000/svg";
		let svg = doc.createElementNS(svgNS, "svg");
		svg.setAttribute("viewBox", "0 0 320 170"); svg.setAttribute("role", "img");
		svg.setAttribute("aria-label", "ATR 当前对象局部关系图");
		svg.style.width = "100%"; svg.style.minHeight = "150px";
		let nodes = [focusNode, ...relatedNodes.filter(node => node.id !== focusNode.id).slice(0, 6)];
		let positions = new Map([[focusNode.id, [160, 82]]]);
		let ring = nodes.slice(1); ring.forEach((node, index) => {
			let angle = (-Math.PI / 2) + index * (Math.PI * 2 / Math.max(ring.length, 1));
			positions.set(node.id, [160 + Math.cos(angle) * 105, 82 + Math.sin(angle) * 58]);
		});
		let ids = new Set(nodes.map(node => node.id));
		for (let edge of this.activeGraph?.edges || []) {
			if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
			let [x1, y1] = positions.get(edge.source), [x2, y2] = positions.get(edge.target);
			let line = doc.createElementNS(svgNS, "line");
			for (let [key, value] of Object.entries({ x1, y1, x2, y2 })) line.setAttribute(key, value);
			line.setAttribute("stroke", "#a9b6c5"); line.setAttribute("stroke-width", "1.5");
			let title = doc.createElementNS(svgNS, "title"); title.textContent = edge.relation; line.append(title); svg.append(line);
		}
		let colors = {
			paper: "#276fbf", knowledge_concept: "#7858a6", concept_map: "#7858a6",
			real_world_tension: "#d97706", reality_signal_gap: "#64748b", research_question: "#bc5b12",
			research_problem: "#b45309", derived_research_question: "#c2410c", claim: "#28796c",
		};
		for (let node of nodes) {
			let [x, y] = positions.get(node.id), group = doc.createElementNS(svgNS, "g");
			group.style.cursor = "pointer"; group.setAttribute("tabindex", "0");
			let circle = doc.createElementNS(svgNS, "circle"); circle.setAttribute("cx", x); circle.setAttribute("cy", y);
			circle.setAttribute("r", node.id === focusNode.id ? "13" : "10");
			let knowledgeStatusColor = {
				BOUNDED_SOURCE_REVIEWED: "#28796c",
				PARTIALLY_SOURCE_REVIEWED: "#7858a6",
				CHALLENGED_BY_COLLISION_REVIEW: "#c2410c",
				PENDING_ADDITIONAL_SOURCE_REVIEW: "#64748b",
			};
			let fill = node.kind === "knowledge_concept"
				? (knowledgeStatusColor[node.data?.review_status] || colors[node.kind])
				: colors[node.kind];
			circle.setAttribute("fill", fill || "#64748b"); circle.setAttribute("stroke", "white"); circle.setAttribute("stroke-width", "2");
			let text = doc.createElementNS(svgNS, "text"); text.setAttribute("x", x); text.setAttribute("y", y + 24);
			text.setAttribute("text-anchor", "middle"); text.setAttribute("font-size", "9"); text.setAttribute("fill", "currentColor");
			text.textContent = String(node.label || node.id).slice(0, 24) + (String(node.label || node.id).length > 24 ? "…" : "");
			let title = doc.createElementNS(svgNS, "title"); title.textContent = node.label + " · " + node.kind
				+ (node.data?.review_status ? " · " + node.data.review_status : "");
			group.append(circle, text, title); group.addEventListener("click", () => openNode(node));
			group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") openNode(node); });
			svg.append(group);
		}
		parent.append(svg);
		if (!relatedNodes.length) {
			this.appendPaneText(doc, parent, "只显示当前对象：附近尚无该类已落盘节点，不补造连接。");
		}
		return svg;
	},

	appendReadingVisualContext(doc, parent, focusNode, item) {
		let header = this.htmlElement(doc, "div");
		header.style.padding = "4px 2px";
		this.appendPaneText(doc, header, "与原文同时核对", true);
		this.appendPaneText(doc, header, "上方是人的可编辑 Zotero Note；下方只显示当前来源附近已经落盘的知识与问题关系。两块图均可折叠。", false);
		parent.append(header);
		let openNode = async node => {
			if (node.kind === "paper") return this.openSourceForCoReading(node);
			if (node.kind === "research_program") return this.openProgramNode(node);
			let object = (this.activeNativeMap?.objects || []).find(candidate => candidate.graph_node_id === node.id);
			if (!object?.marker) return;
			let note = await this.findMarkedNote(object.marker);
			if (note) await this.openNoteBesideReader(note);
		};
		let knowledge = this.nearestGraphNodes(focusNode?.id, new Set(["knowledge_concept", "concept_map"]));
		let knowledgeBody = this.appendDockDisclosure(
			doc, parent, "readingKnowledge", "知识定位", [], true, false,
		);
		this.appendMiniGraph(doc, knowledgeBody, focusNode, knowledge, openNode);
		let problems = this.nearestGraphNodes(focusNode?.id, new Set([
			"real_world_tension", "reality_signal_gap", "research_question", "research_problem",
			"derived_research_question", "claim",
		]));
		let problemBody = this.appendDockDisclosure(
			doc, parent, "readingProblem", "现实问题 → 研究问题", [], true, false,
		);
		this.appendMiniGraph(doc, problemBody, focusNode, problems, openNode);
		if (focusNode?.kind === "paper") {
			this.appendPaneText(doc, parent, "当前来源支持：" + (focusNode.data?.supports || "未记录"));
			this.appendPaneText(doc, parent, "不能据此推出：" + (
				focusNode.data?.does_not_support || focusNode.data?.does_not_establish || "未记录"
			), true);
			this.appendPendingReviewSummary(doc, parent, null, focusNode.data?.source_id);
		}
		this.appendPaneButton(doc, parent, "打开完整 ATR 定位", () => {
			let win = Zotero.getMainWindow();
			let tabID = win?.Zotero_Tabs?.selectedID;
			let itemContext = win?.ZoteroContextPane?.context?._getItemContext?.(tabID);
			return itemContext?.scrollToPane?.(this.sectionID);
		});
		this.appendPaneButton(doc, parent, "便携镜像", () => this.openCompanionWindow(focusNode, item));
	},

	appendPortfolioGraph(doc, parent, openNode) {
		let graph = this.activeGraph || { nodes: [], edges: [] };
		let portfolio = (graph.nodes || []).find(node => node.kind === "research_portfolio");
		let programs = (graph.nodes || []).filter(node => node.kind === "research_program");
		if (!portfolio || !programs.length) return null;
		let byID = Object.fromEntries((graph.nodes || []).map(node => [node.id, node]));
		let programEdges = (graph.edges || []).filter(edge =>
			edge.source === portfolio.id && edge.relation === "registers_separate_program_authority"
		);
		programs = programEdges.map(edge => byID[edge.target]).filter(Boolean);
		let branches = new Map(programs.map(program => [program.id, (graph.edges || [])
			.filter(edge => edge.source === program.id && edge.relation === "retains_legacy_branch_as_input")
			.map(edge => byID[edge.target]).filter(Boolean)]));
		let svgNS = "http://www.w3.org/2000/svg";
		let width = 680, height = 430;
		let svg = doc.createElementNS(svgNS, "svg");
		svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.setAttribute("role", "img");
		svg.setAttribute("aria-label", "ATR portfolio 到 program 与历史分支总览图");
		svg.style.width = "100%"; svg.style.minHeight = "300px";
		let rootX = width / 2, rootY = 32;
		let positions = new Map([[portfolio.id, [rootX, rootY]]]);
		programs.forEach((program, index) => positions.set(program.id, [
			55 + index * ((width - 110) / Math.max(programs.length - 1, 1)), 112,
		]));
		for (let program of programs) {
			let [programX] = positions.get(program.id), rows = branches.get(program.id) || [];
			rows.forEach((branch, index) => {
				let column = (index % 3) - 1, row = Math.floor(index / 3);
				positions.set(branch.id, [programX + column * 22, 190 + row * 42]);
			});
		}
		let addLine = (source, target, strong = false) => {
			let [x1, y1] = positions.get(source.id), [x2, y2] = positions.get(target.id);
			let line = doc.createElementNS(svgNS, "line");
			for (let [key, value] of Object.entries({ x1, y1, x2, y2 })) line.setAttribute(key, value);
			line.setAttribute("stroke", strong ? "#718096" : "#cbd5e1");
			line.setAttribute("stroke-width", strong ? "2" : "1.2"); svg.append(line);
		};
		for (let program of programs) {
			addLine(portfolio, program, true);
			for (let branch of branches.get(program.id) || []) addLine(program, branch);
		}
		let addNode = (node, radius, color, label = null) => {
			let [x, y] = positions.get(node.id), group = doc.createElementNS(svgNS, "g");
			group.style.cursor = "pointer"; group.setAttribute("tabindex", "0");
			let circle = doc.createElementNS(svgNS, "circle");
			circle.setAttribute("cx", x); circle.setAttribute("cy", y); circle.setAttribute("r", radius);
			circle.setAttribute("fill", color); circle.setAttribute("stroke", "white"); circle.setAttribute("stroke-width", "2");
			group.append(circle);
			if (label) {
				let text = doc.createElementNS(svgNS, "text"); text.setAttribute("x", x); text.setAttribute("y", y + radius + 14);
				text.setAttribute("text-anchor", "middle"); text.setAttribute("font-size", node.kind === "research_portfolio" ? "11" : "9");
				text.setAttribute("fill", "currentColor"); text.textContent = label; group.append(text);
			}
			let title = doc.createElementNS(svgNS, "title");
			title.textContent = node.label + (node.data?.recorded_stage ? " · " + node.data.recorded_stage : "")
				+ (node.data?.alignment_disposition ? " · " + node.data.alignment_disposition : "")
				+ (node.data?.mapped_artifact_count ? " · LEGACY_MAPPED×" + node.data.mapped_artifact_count : "");
			group.append(title); group.addEventListener("click", () => openNode(node));
			group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") openNode(node); });
			svg.append(group);
		};
		addNode(portfolio, 15, "#334e68", "Portfolio");
		for (let [index, program] of programs.entries()) {
			let disposition = program.data?.posterior_disposition || "PENDING";
			let color = disposition === "REFRAME" ? "#b45309" : disposition === "NEEDS_EVIDENCE" ? "#7c3aed" : "#276fbf";
			addNode(program, 12, color, `${index + 1} · ${disposition}`);
			for (let branch of branches.get(program.id) || []) addNode(branch, 7, "#94a3b8");
		}
		parent.append(svg);
		let mappedArtifacts = [...branches.values()].flat()
			.reduce((total, branch) => total + Number(branch.data?.mapped_artifact_count || 0), 0);
		this.appendPaneText(doc, parent, `1 个 portfolio · ${programs.length} 个独立 program authority · ${
			[...branches.values()].reduce((total, rows) => total + rows.length, 0)
		} 条只读历史 branch · ${mappedArtifacts} 个逐项 LEGACY_MAPPED sidecar。橙色=REFRAME，紫色=NEEDS_EVIDENCE；这些是 worker 输出而不是 gate。点击 program 进入对应 Zotero topic；点击灰色历史节点打开只读导航 Note。`);
		let reviewDetails = this.htmlElement(doc, "details");
		reviewDetails.style.margin = "8px 0";
		let pending = programs.filter(program =>
			(program.data?.owner_review_status || "PENDING_HUMAN_OWNER_REVIEW") === "PENDING_HUMAN_OWNER_REVIEW"
		);
		let reviewSummary = this.htmlElement(doc, "summary", `待我的 owner review · ${pending.length}`);
		reviewSummary.style.cursor = "pointer";
		reviewSummary.style.fontWeight = "600";
		reviewDetails.append(reviewSummary);
		let reviewControls = this.htmlElement(doc, "div");
		reviewControls.style.padding = "6px 2px 0 10px";
		reviewDetails.append(reviewControls);
		this.appendPaneText(doc, reviewControls, "每个入口先切换到 child authority，再打开其碰撞复核 Note；不会替你接受 worker 建议。", true);
		for (let [index, program] of pending.entries()) {
			this.appendPaneButton(
				doc,
				reviewControls,
				`${index + 1} · ${program.data?.posterior_disposition || "PENDING"} · ${program.label}`,
				() => this.openProgramReviewNode(program),
			);
		}
		parent.append(reviewDetails);
		return svg;
	},

	appendCoReadingDock(doc, body, focusNode, item, portable = false) {
		if (!this.dockRenderLogged) {
			this.dockRenderLogged = true;
			this.appendRuntimeStatus("co_reading_dock_rendered", {
				focus_node_id: focusNode?.id || null,
				panels: ["process", "knowledge", "problem", "detail"],
			}).catch(error => this.log("could not record co-reading dock render: " + error));
		}
		let subject = (this.activeGraph?.nodes || []).find(node => node.kind === "atr_v2_subject" && node.data?.active);
		let header = this.htmlElement(doc, "div"); header.style.padding = "8px";
		header.style.border = "1px solid var(--fill-quinary, #d9e2ec)"; header.style.borderRadius = "7px";
		this.appendPaneText(doc, header, this.topicTitle(), true);
		this.appendPaneText(doc, header, (subject?.data?.state || "LEGACY") + " · " + (focusNode?.label || "当前 Topic"));
		if (this.activeRunRecord?.view_role === "REGISTERED_V2_RUN") {
			this.appendPaneButton(doc, header, "返回研究组合", () => this.openPortfolio(), true);
		}
		if (portable) {
			if (focusNode?.kind === "paper") {
				this.appendPaneButton(doc, header, "回到原文与人的笔记", () => {
					return this.openSourceForCoReading(focusNode, item);
				}, true);
			}
			else {
				this.appendPaneButton(doc, header, "打开这份 Zotero Note", async () => {
					await this.openNativeNote(await this.coReadingNote(focusNode, item));
				}, true);
			}
			this.appendPaneText(doc, header, "便携窗只显示当前 ATR 定位；正文与人的理解仍留在 Zotero Reader / Note。", false);
		}
		else {
			if (focusNode?.kind === "paper") {
				this.appendPaneButton(doc, header, "阅读原文并记录我的理解", () => {
					return this.openSourceForCoReading(focusNode, item);
				}, true);
			}
			else {
				this.appendPaneButton(doc, header, "打开当前 Zotero Note", async () => {
					await this.openNativeNote(await this.coReadingNote(focusNode, item));
				}, true);
			}
			this.appendPaneButton(doc, header, "便携显示 ATR 定位", () => this.openCompanionWindow(focusNode, item));
			this.appendPaneText(doc, header, "正文、批注和人的 Note 使用 Zotero 原生界面；下面只保留可折叠的研究定位。", false);
		}
		body.append(header);
		let openNode = async node => {
			if (node.kind === "paper") return this.openSourceForCoReading(node);
			if (node.kind === "research_program") return this.openProgramNode(node);
			let object = (this.activeNativeMap?.objects || []).find(candidate => candidate.graph_node_id === node.id);
			if (!object?.marker) return;
			let note = await this.findMarkedNote(object.marker); if (note) await this.openNoteBesideReader(note);
		};
		let processRows = (this.activeGraph?.timeline || []).slice(-4).reverse().map(item => ({
			label: (item.label || item.kind) + " · " + (item.at || "未记录时间"),
		}));
		let processBody = this.appendDockDisclosure(doc, body, "process", "项目历史 / 过程", processRows, false);
		this.appendPortfolioGraph(doc, processBody, openNode);
		let knowledge = this.nearestGraphNodes(focusNode?.id, new Set(["knowledge_concept", "concept_map"]));
		let knowledgeBody = this.appendDockDisclosure(doc, body, "knowledge", "知识定位", [], false, false);
		this.appendMiniGraph(doc, knowledgeBody, focusNode, knowledge, openNode);
		this.appendPaneText(doc, knowledgeBody, "知识状态：绿色=受限原文支撑；紫色=部分支撑；橙色=被碰撞复核挑战；灰色=等待更多来源。");
		let problems = this.nearestGraphNodes(focusNode?.id, new Set([
			"real_world_tension", "reality_signal_gap", "research_question", "research_problem", "derived_research_question", "claim",
		]));
		let problemBody = this.appendDockDisclosure(doc, body, "problem", "现实问题 / 研究问题", [], true, false);
		this.appendMiniGraph(doc, problemBody, focusNode, problems, openNode);
		let detailRows = [];
		if (focusNode) detailRows.push({ label: focusNode.kind + " · " + focusNode.label });
		if (focusNode?.kind === "paper") {
			let data = focusNode.data || {};
			let humanReviews = this.pendingReviewItems(null, data.source_id);
			detailRows.push({ label: "这篇来源支持：" + (data.supports || "未记录") });
			detailRows.push({ label: "不能据此推出：" + (data.does_not_support || data.does_not_establish || "未记录") });
			detailRows.push({ label: "worker 全文检查：" + (data.worker_inspection_state || data.fulltext_state || "未记录") });
			detailRows.push({ label: humanReviews.length
				? "人的阅读：已有 " + humanReviews.length + " 条 Note / annotation 等待复审"
				: "人的阅读：当前投影尚无 Note / annotation 复审记录" });
			detailRows.push({ label: "Zotero 附件：" + (data.zotero_attachment_state || "未记录") + " · 快照：" + (data.zotero_snapshot_state || "未记录") });
			for (let span of data.inspection_spans || []) detailRows.push({
				label: (span.locator || "未记录定位") + " · " + (span.observation || "未记录观察"),
			});
		}
		return this.appendDockDisclosure(doc, body, "detail", "当前对象", detailRows, true);
	},

	async ensureActiveGraph() {
		if (this.activeGraph) return this.activeGraph;
		return this.loadProjection(await this.defaultRun());
	},

	async renderItemPane({ doc, body, item, setSectionSummary }) {
		body.replaceChildren();
		await this.ensureActiveGraph();
		let marker = item.isNote?.() ? this.markerFromNote(item) : {};
		let decisionNode = marker.graphNode
			? (this.activeGraph.nodes || []).find(node => node.id === marker.graphNode)
			: marker.problem
				? (this.activeGraph.nodes || []).find(node => node.kind === "research_problem" && node.data?.problem_id === marker.problem)
				: marker.claim
					? (this.activeGraph.nodes || []).find(node => node.kind === "claim" && node.data?.claim_id === marker.claim)
					: null;
		let sourceID = marker.source || this.sourceIDFromItem(item);
		let source = sourceID ? this.sourceByID(sourceID) : null;
		let nativeObject = decisionNode
			? (this.activeNativeMap?.objects || []).find(object => object.graph_node_id === decisionNode.id)
			: null;
		let focusNode = decisionNode || source;
		this.companionFocusNode = focusNode || null;
		this.companionItem = item;
		body = this.appendCoReadingDock(doc, body, focusNode, item);
		if (this.companionWindowAlive()) await this.renderCompanionWindow();

		if (marker.process) {
			setSectionSummary("ATR 实际研究过程 · " + this.topicTitle());
			this.appendPaneText(doc, body, this.topicTitle(), true);
			this.appendPaneText(doc, body, "已记录事件：" + (this.activeGraph.timeline || []).length);
			this.appendPaneText(doc, body, "该 Note 只投影实际落盘事件，不补造缺失历史。");
			this.appendPendingReviewSummary(doc, body);
			this.appendPaneButton(doc, body, "打开 Topic Note 写综合判断", async () => {
				await this.openNativeNote(await this.ensureTopicNote());
			}, true);
			return;
		}

		if (marker.reviewAssessment && decisionNode?.kind === "human_review_assessment") {
			setSectionSummary("共创复核 · " + (decisionNode.data?.outcome || "UNSPECIFIED"));
			this.appendPaneText(doc, body, decisionNode.data?.finding || "未记录复核结论", true);
			this.appendPaneText(doc, body, "后续产物：" + (decisionNode.data?.required_followup_artifact_kind || "NONE"));
			this.appendPaneText(doc, body, "该复核不会自行改变 lifecycle；旧节点和旧边继续作为历史保留。");
			let byID = Object.fromEntries((this.activeGraph.nodes || []).map(node => [node.id, node]));
			let targets = (this.activeGraph.edges || [])
				.filter(edge => edge.source === decisionNode.id
					&& ["preserves_object_after_review", "requests_new_version_after_review"].includes(edge.relation))
				.map(edge => byID[edge.target]).filter(Boolean);
			for (let target of targets) {
				if (target.kind === "paper") {
					this.appendPaneButton(doc, body, "阅读 · " + target.label, () => this.openSourceInReader(target));
					continue;
				}
				let object = (this.activeNativeMap?.objects || []).find(candidate => candidate.graph_node_id === target.id);
				if (object?.marker) this.appendPaneButton(doc, body, "打开 · " + target.label, async () => {
					let targetNote = await this.findMarkedNote(object.marker);
					if (targetNote) await this.openNativeNote(targetNote);
				});
			}
			this.appendPaneButton(doc, body, "打开实际研究过程", async () => this.openNativeNote(await this.ensureProcessNote()), true);
			return;
		}

		if (marker.run) {
			setSectionSummary("ATR Topic · " + this.topicTitle());
			this.appendPaneText(doc, body, this.topicTitle(), true);
			let subject = (this.activeGraph.nodes || [])
				.find(node => node.kind === "atr_v2_subject" && node.data?.active);
			this.appendPaneText(doc, body, "当前阶段：" + (subject?.data?.state || "未记录"));
			this.appendPendingReviewSummary(doc, body);
			this.appendPaneButton(doc, body, "打开实际研究过程", async () => {
				await this.openNativeNote(await this.ensureProcessNote());
			}, true);
			this.appendPaneButton(doc, body, "定位 Topic Collection", async () => {
				let collection = await this.ensureTopicCollection();
				let win = Zotero.getMainWindow();
				win.Zotero_Tabs.select("zotero-pane");
				await win.ZoteroPane.collectionsView.selectCollection(collection.id);
			}, true);
			let firstSource = (this.activeGraph.nodes || [])
				.find(node => node.kind === "paper" && node.data?.source_id);
			if (firstSource) {
				this.appendPaneButton(doc, body, "打开第一篇来源", () => this.openSourceInReader(firstSource));
			}
			return;
		}

		if (decisionNode?.kind === "knowledge_concept") {
			setSectionSummary("知识节点 · " + decisionNode.label);
			this.appendPaneText(doc, body, decisionNode.label, true);
			this.appendPaneText(doc, body, "知识核验状态：" + (decisionNode.data?.review_status || "PENDING_SOURCE_REVIEW"), true);
			this.appendPaneText(doc, body, "定义：" + (decisionNode.data?.definition || "尚未记录可审查定义"));
			this.appendPaneText(doc, body, "不能推出：" + (decisionNode.data?.does_not_establish || "尚未记录边界"));
			for (let span of (decisionNode.data?.evidence_spans || []).slice(0, 4)) {
				this.appendPaneText(doc, body, (span.source_id || "未记录来源") + " · "
					+ (span.locator || "未记录定位") + " · " + (span.relation || "未记录关系")
					+ "：" + (span.observation || "未记录观察"));
			}
			let byID = Object.fromEntries((this.activeGraph.nodes || []).map(node => [node.id, node]));
			let linkedSources = (this.activeGraph.edges || [])
				.filter(edge => edge.source === decisionNode.id || edge.target === decisionNode.id)
				.map(edge => byID[edge.source === decisionNode.id ? edge.target : edge.source])
				.filter(node => node?.kind === "paper");
			for (let linked of linkedSources.slice(0, 8)) {
				this.appendPaneButton(doc, body, "阅读并记录 · " + linked.label, () => this.openSourceForCoReading(linked));
			}
			this.appendPendingReviewSummary(doc, body, decisionNode.id);
			if (item.isNote?.() && nativeObject?.review_role !== "HISTORICAL_VERSION") {
				this.appendReviewStanceButtons(doc, body, async () => item);
			}
			this.appendPaneButton(doc, body, "打开 Topic Note", async () => this.openNativeNote(await this.ensureTopicNote()));
			return;
		}

		if (["real_world_tension", "reality_signal_gap", "research_question", "derived_research_question"].includes(decisionNode?.kind)) {
			let typeLabel = {
				real_world_tension: "现实世界张力",
				reality_signal_gap: "现实证据缺口",
				research_question: "前沿研究问题",
				derived_research_question: "细粒度研究问题",
			}[decisionNode.kind];
			setSectionSummary(typeLabel + " · " + decisionNode.label);
			this.appendPaneText(doc, body, decisionNode.label, true);
			if (decisionNode.kind === "real_world_tension") {
				this.appendPaneText(doc, body, "行动者：" + (decisionNode.data?.actor || "未记录"));
				this.appendPaneText(doc, body, "现实后果：" + (decisionNode.data?.material_consequence || "未记录"));
				this.appendPaneText(doc, body, "不能推出：" + (decisionNode.data?.does_not_establish || "未记录"));
			}
			else if (decisionNode.kind === "reality_signal_gap") {
				this.appendPaneText(doc, body, "受限检索结论：" + (decisionNode.data?.decision || "未记录"), true);
				this.appendPaneText(doc, body, "为什么不能形成张力：" + (decisionNode.data?.reason || "未记录"));
				this.appendPaneText(doc, body, "缺失的来源功能：" + (decisionNode.data?.missing_source_function || "未记录"));
				this.appendPaneText(doc, body, "下一步合法工作：" + (decisionNode.data?.next_legal_work || "未记录"));
				this.appendPaneText(doc, body, "不能推出：" + (decisionNode.data?.does_not_establish || "未记录"));
			}
			else if (decisionNode.kind === "research_question") {
				this.appendPaneText(doc, body, "竞争解释：" + ((decisionNode.data?.explanations || []).join("；") || "未记录"));
				this.appendPaneText(doc, body, "刷新条件：" + (decisionNode.data?.freshness || "未记录"));
			}
			else {
				this.appendPaneText(doc, body, "最小判别：" + (decisionNode.data?.smallest_discriminator || "未记录"));
				this.appendPaneText(doc, body, "不能推出：" + (decisionNode.data?.does_not_establish || "未记录"));
			}
			let byID = Object.fromEntries((this.activeGraph.nodes || []).map(node => [node.id, node]));
			let linkedSources = (this.activeGraph.edges || [])
				.filter(edge => edge.source === decisionNode.id || edge.target === decisionNode.id)
				.map(edge => byID[edge.source === decisionNode.id ? edge.target : edge.source])
				.filter(node => node?.kind === "paper");
			for (let linked of linkedSources.slice(0, 8)) {
				this.appendPaneButton(doc, body, "阅读 · " + linked.label, () => this.openSourceInReader(linked));
			}
			this.appendPendingReviewSummary(doc, body, decisionNode.id);
			if (item.isNote?.() && nativeObject?.review_role !== "HISTORICAL_VERSION") {
				this.appendReviewStanceButtons(doc, body, async () => item);
			}
			this.appendPaneButton(doc, body, "打开 Topic Note", async () => this.openNativeNote(await this.ensureTopicNote()));
			return;
		}

		if (decisionNode?.kind === "research_program") {
			setSectionSummary("研究计划 · " + decisionNode.label);
			this.appendPaneText(doc, body, decisionNode.label, true);
			this.appendPaneText(doc, body, "worker 建议（不是 gate）：" + (decisionNode.data?.posterior_disposition || "PENDING"), true);
			this.appendPaneText(doc, body, "人的 owner review：" + (decisionNode.data?.owner_review_status || "PENDING_HUMAN_OWNER_REVIEW"));
			this.appendPaneText(doc, body, "残存边界：" + (decisionNode.data?.surviving_boundary || "未记录"));
			this.appendPaneText(doc, body, "下一证据：" + ((decisionNode.data?.next_evidence || []).join("；") || "未记录"));
			this.appendPaneButton(doc, body, "进入 child 并开始 owner review", () => this.openProgramReviewNode(decisionNode), true);
			this.appendPaneButton(doc, body, "只进入 child topic", () => this.openProgramNode(decisionNode));
			this.appendPaneText(doc, body, "owner review 输入写入 child 的碰撞复核 Note；portfolio 只负责导航，不拥有 child lifecycle。", false);
			return;
		}

		if (decisionNode?.kind === "zotero_source_reconciliation") {
			setSectionSummary("Zotero 来源对账 · 只读");
			let summary = decisionNode.data?.summary || {};
			this.appendPaneText(doc, body, "严格身份匹配：" + String(summary.exact_identity_matches || 0), true);
			this.appendPaneText(doc, body, "Zotero 本地 PDF：" + String(summary.local_fulltext || 0));
			this.appendPaneText(doc, body, "只有书目无本地 PDF：" + String(summary.items_without_local_fulltext || 0));
			this.appendPaneText(doc, body, "仍需身份复核：" + String(summary.identity_review_required || summary.title_matches_requiring_review || 0));
			this.appendPaneText(doc, body, "未在 Zotero 找到：" + String(summary.not_found || 0));
			this.appendPaneText(doc, body, "本地可用不等于全文已检查，不会自动改变 claim、gate、route 或 lifecycle。", false);
			let byID = Object.fromEntries((this.activeGraph.nodes || []).map(node => [node.id, node]));
			let linked = (this.activeGraph.edges || [])
				.filter(edge => edge.source === decisionNode.id && edge.relation === "confirms_zotero_local_availability")
				.map(edge => byID[edge.target]).filter(Boolean);
			for (let paper of linked) {
				this.appendPaneButton(doc, body, "打开 Zotero 来源 · " + paper.label, () => this.openSourceForCoReading(paper));
			}
			return;
		}

		if (decisionNode?.kind === "repo_pdf_zotero_handoff_audit") {
			setSectionSummary("Repo PDF → Zotero · 待显式打开");
			let summary = decisionNode.data?.summary || {};
			this.appendPaneText(doc, body, "repo 已缓存 PDF：" + String(summary.repo_cached_pdfs || 0), true);
			this.appendPaneText(doc, body, "可在显式打开时导入：" + String(summary.import_ready || 0));
			this.appendPaneText(doc, body, "仍被阻止：" + String(summary.blocked || 0));
			this.appendPaneText(doc, body, "这里没有自动写 Zotero。打开具体来源时仍会重新校验路径与 SHA-256。", false);
			let byID = Object.fromEntries((this.activeGraph.nodes || []).map(node => [node.id, node]));
			let linked = (this.activeGraph.edges || [])
				.filter(edge => edge.source === decisionNode.id && edge.relation === "authorizes_explicit_zotero_stored_copy")
				.map(edge => byID[edge.target]).filter(Boolean);
			for (let paper of linked) {
				this.appendPaneButton(doc, body, "打开并交给 Zotero 管理 · " + paper.label, () => this.openSourceForCoReading(paper));
			}
			return;
		}

		if (decisionNode?.kind === "collision_review") {
			setSectionSummary("碰撞复核 · " + (decisionNode.data?.disposition || "待判断"));
			this.appendPaneText(doc, body, "worker 建议（不是 gate）：" + (decisionNode.data?.disposition || "未记录"), true);
			this.appendPaneText(doc, body, "残存可检验边界：" + (decisionNode.data?.surviving_boundary || "未记录"));
			this.appendPaneText(doc, body, "覆盖限制：" + ((decisionNode.data?.coverage_limits || []).join("；") || "未记录"));
			this.appendPaneText(doc, body, "下一证据：" + ((decisionNode.data?.next_evidence || []).join("；") || "未记录"));
			let linkedSources = (nativeObject?.linked_source_ids || [])
				.map(sourceID => this.sourceByID(sourceID)).filter(Boolean);
			for (let linked of linkedSources) {
				this.appendPaneButton(doc, body, "核对碰撞来源 · " + linked.label, () => this.openSourceForCoReading(linked));
			}
			let parentObject = (this.activeNativeMap?.objects || []).find(candidate =>
				candidate.graph_node_id === nativeObject?.parent_graph_node_id
			);
			if (parentObject?.marker) {
				this.appendPaneButton(doc, body, "打开父问题卡", async () => {
					let parent = await this.findMarkedNote(parentObject.marker);
					if (parent) await this.openNativeNote(parent);
				});
			}
			this.appendPendingReviewSummary(doc, body, decisionNode.id);
			if (item.isNote?.()) {
				this.appendOwnerRouteReviewControls(doc, body, async () => this.ensureOwnerRouteReviewTemplate(item));
				this.appendReviewStanceButtons(doc, body, async () => item);
			}
			return;
		}

		if (decisionNode?.kind === "topic_route_draft") {
			setSectionSummary("待独立复核的 Topic Route · " + decisionNode.data?.selected_track);
			this.appendPaneText(doc, body, decisionNode.label, true);
			this.appendPaneText(doc, body, "候选知识路径：" + (decisionNode.data?.selected_track || "未记录"));
			this.appendPaneText(doc, body, "复核后可能进入：" + (decisionNode.data?.next_stage || "未记录"));
			this.appendPaneText(doc, body, "当前仍为：" + (decisionNode.data?.review_status || "PENDING"), true);
			this.appendPaneText(doc, body, "不能推出：" + (decisionNode.data?.does_not_establish || "不能授权 lifecycle transition"));
			this.appendReviewStanceButtons(doc, body, async () => item);
			this.appendPaneButton(doc, body, "打开实际研究过程", async () => this.openNativeNote(await this.ensureProcessNote()));
			return;
		}

		if (decisionNode) {
			let isProblem = decisionNode.kind === "research_problem";
			setSectionSummary((isProblem ? "研究问题" : "待审查断言") + " · " + decisionNode.label);
			this.appendPaneText(doc, body, decisionNode.label, true);
			if (isProblem) {
				this.appendPaneText(doc, body, "最小判别：" + (decisionNode.data?.discriminator || decisionNode.data?.smallest_discriminator || "未记录"));
				this.appendPaneText(doc, body, "证伪条件：" + (decisionNode.data?.falsifier || decisionNode.data?.minimum_falsifier || "未记录"));
			}
			else {
				this.appendPaneText(doc, body, "状态：" + (decisionNode.data?.status || "未记录"));
				this.appendPaneText(doc, body, "禁止外推：" + ((decisionNode.data?.forbidden_claims || []).join("；") || "未记录"));
			}
			let byID = Object.fromEntries((this.activeGraph.nodes || []).map(node => [node.id, node]));
			let linkedSources = (this.activeGraph.edges || [])
				.filter(edge => edge.source === decisionNode.id || edge.target === decisionNode.id)
				.map(edge => byID[edge.source === decisionNode.id ? edge.target : edge.source])
				.filter(node => node?.kind === "paper");
			for (let linked of linkedSources.slice(0, 5)) {
				this.appendPaneButton(doc, body, "阅读并记录 · " + linked.label, () => this.openSourceForCoReading(linked));
			}
			this.appendPendingReviewSummary(doc, body, decisionNode.id);
			if (item.isNote?.() && nativeObject?.review_role !== "HISTORICAL_VERSION") {
				this.appendReviewStanceButtons(doc, body, async () => item);
			}
			this.appendPaneButton(doc, body, "打开 Topic Note", async () => this.openNativeNote(await this.ensureTopicNote()));
			return;
		}

		if (!source) {
			setSectionSummary("当前条目没有 ATR 来源映射");
			this.appendPaneText(doc, body, "当前条目带有 ATR marker，但不在当前 topic 投影中。历史映射不会被自动改写。");
			return;
		}

		setSectionSummary(sourceID + " · " + source.label);
		this.appendPendingReviewSummary(doc, body, null, sourceID);
		let readerTarget = item;
		let sourceItem = item;
		if (sourceItem.isAnnotation?.() && sourceItem.parentItemID) {
			let attachment = Zotero.Items.get(sourceItem.parentItemID);
			if (attachment?.parentItemID) sourceItem = Zotero.Items.get(attachment.parentItemID);
		}
		if (sourceItem.isNote?.() && sourceItem.parentItemID) sourceItem = Zotero.Items.get(sourceItem.parentItemID);
		if (sourceItem.isAttachment?.() && sourceItem.parentItemID) sourceItem = Zotero.Items.get(sourceItem.parentItemID);
		let attached = sourceItem?.getBestAttachment ? await sourceItem.getBestAttachment() : null;
		let canResolve = sourceItem && !attached && Zotero.Attachments.canFindFileForItem(sourceItem);
		let nativeSource = (this.activeNativeMap?.objects || []).find(object =>
			object.object_kind === "source_item" && object.atr_id === sourceID
		);
		let localReady = nativeSource?.local_cache_import_state === "READY";
		let fulltextStatus = attached
			? "全文：已附加到 Zotero"
			: localReady
				? "全文：身份与摘要已核验，点击后复制进 Zotero 管理"
			: source.data?.pdf_url
				? "全文：明确开放 PDF，点击后下载并附加"
				: canResolve
					? "全文：尚未附加，点击后由 Zotero 查找可用 PDF"
					: "全文：仅书目信息，需要机构访问或手工添加 PDF";
		this.appendPaneText(doc, body, fulltextStatus, true);
		let readLabel = item.isAnnotation?.()
			? "定位高亮并打开我的笔记"
			: attached
				? "阅读全文并记录我的理解"
				: localReady
					? "导入 Zotero、阅读并记录理解"
				: source.data?.pdf_url
					? "下载开放全文、阅读并记录理解"
					: "让 Zotero 查找全文并记录理解";
		this.appendPaneButton(doc, body, readLabel, () => this.openSourceForCoReading(source, readerTarget), true);
		this.appendPaneButton(doc, body, "在新标签深度编辑这份来源笔记", async () => {
			let note = await this.ensureSourceReviewNote(source, sourceItem);
			await this.openNativeNote(note);
		});
		this.appendReviewStanceButtons(doc, body, async () => this.ensureSourceReviewNote(source, sourceItem));
	},

	async registerItemPane() {
		if (this.sectionID) return;
		this.sectionID = Zotero.ItemPaneManager.registerSection({
			paneID: "atr-research-context",
			pluginID: this.id,
			header: {
				l10nID: "atr-item-pane-header",
				icon: "chrome://zotero/skin/16/universal/book.svg",
			},
			sidenav: {
				l10nID: "atr-item-pane-sidenav",
				icon: "chrome://zotero/skin/20/universal/save.svg",
			},
			sectionButtons: [{
				type: "openReadingNote",
				icon: "chrome://zotero/skin/16/universal/note.svg",
				l10nID: "atr-item-pane-open-reading-note",
				onClick: ({ item }) => this.openCurrentReadingNote(item),
			}, {
				type: "openCompanion",
				icon: "chrome://zotero/skin/16/universal/open-link.svg",
				l10nID: "atr-item-pane-open-companion",
				onClick: ({ item }) => this.openCompanionWindow(
					this.companionFocusNode,
					item || this.companionItem,
				),
			}],
			onItemChange: ({ item, setEnabled }) => {
				setEnabled(this.hasATRContext(item));
				return true;
			},
			onRender: ({ body }) => {
				body.replaceChildren();
			},
			onAsyncRender: props => this.renderItemPane(props),
		});
		this.log("native item pane section registered: " + this.sectionID);
		await this.appendRuntimeStatus("native_item_pane_registered", {
			pane_id: this.sectionID,
		});
	},

	unregisterItemPane() {
		if (!this.sectionID) return;
		Zotero.ItemPaneManager.unregisterSection(this.sectionID);
		this.sectionID = null;
	},

	async noteChanged(item, extraData) {
		if (this.suppressedNotifierItemIDs.has(item.id)) return;
		let changedFields = Object.keys(extraData?.changed || {});
		if (changedFields.length && changedFields.every(field => field === "collections")) {
			this.log("ignored non-cognitive Note metadata change: " + item.key);
			return;
		}
		let noteHTML = item.getNote();
		let noteText = this.plainNote(noteHTML);
		let marker = this.markerFromNote(item);
		if (marker.reviewAssessment) return;
		if (!marker.run && !marker.source && !marker.claim && !marker.problem && !marker.knowledge
			&& !marker.tension && !marker.realitySignalGap && !marker.researchQuestion && !marker.derivedQuestion && !marker.topicRoute
			&& !marker.collisionReview) return;
		let stance = /ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING|HISTORICAL_REFERENCE_ONLY)/
			.exec(noteText)?.[1] || "UNSPECIFIED";
		let ownerRouteInput = /ATR Owner Route Input:\s*(PENDING|ACCEPT_REFRAME|REQUEST_MORE_EVIDENCE|PARK_TOPIC|RETIRE_CANDIDATE)/
			.exec(noteText)?.[1] || null;
		let ownerRouteRationale = /ATR Owner Route Rationale:\s*(.*?)(?=\s+可选输入：|$)/
			.exec(noteText)?.[1]?.trim() || null;
		let locator = /ATR Source Locator:\s*([^<]*)<\/p>/i.exec(noteHTML)?.[1]?.trim() || null;
		await this.appendHumanInput({
			schema_version: "0.2",
			event: "human_note_modified",
			input_origin: "ZOTERO_NOTIFIER",
			at: new Date().toISOString(),
			atr_run: marker.run,
			atr_source_id: marker.source,
			atr_claim_id: marker.claim,
			atr_problem_id: marker.problem,
			atr_knowledge_node_id: marker.knowledge,
			atr_tension_node_id: marker.tension,
			atr_reality_signal_gap_node_id: marker.realitySignalGap,
			atr_research_question_node_id: marker.researchQuestion,
			atr_derived_question_node_id: marker.derivedQuestion,
			atr_topic_route_node_id: marker.topicRoute,
			atr_collision_review_id: marker.collisionReview,
			atr_research_node_id: marker.tension || marker.realitySignalGap || marker.researchQuestion || marker.derivedQuestion,
			atr_graph_node_id: marker.graphNode,
			review_stance: stance,
			owner_route_input: ownerRouteInput,
			owner_route_rationale: ownerRouteRationale,
			source_locator: locator,
			zotero_note_key: item.key,
			zotero_parent_key: item.parentItem?.key || null,
			note_html: noteHTML,
			notifier: extraData || null,
		});
	},

	async annotationChanged(item, extraData) {
		let sourceID = this.sourceIDFromItem(item);
		if (!sourceID) return;
		let sourceNode = (this.activeGraph?.nodes || []).find(node =>
			node.kind === "paper" && node.data?.source_id === sourceID
		);
		let attachment = Zotero.Items.get(item.parentItemID);
		let libraryID = attachment?.libraryID || item.libraryID;
		let scope = "library";
		if (libraryID !== Zotero.Libraries.userLibraryID) {
			try {
				scope = "groups/" + Zotero.Groups.getGroupIDFromLibraryID(libraryID);
			}
			catch (error) {
				this.log("cannot create annotation deep link for unsupported library: " + error);
				scope = null;
			}
		}
		let position = item.annotationPosition;
		if (typeof position === "string") {
			try { position = JSON.parse(position); }
			catch (_) { position = null; }
		}
		let page = Number.isInteger(position?.pageIndex) ? position.pageIndex + 1 : null;
		let deepLink = scope && attachment?.key
			? "zotero://open-pdf/" + scope + "/items/" + encodeURIComponent(attachment.key)
				+ "?" + (page ? "page=" + page + "&" : "")
				+ "annotation=" + encodeURIComponent(item.key)
			: null;
		await this.appendHumanInput({
			schema_version: "0.2",
			event: "human_annotation_modified",
			input_origin: "ZOTERO_NOTIFIER",
			at: new Date().toISOString(),
			atr_run: this.activeGraph?.run || null,
			atr_source_id: sourceID,
			atr_graph_node_id: sourceNode?.id || null,
			zotero_annotation_key: item.key,
			zotero_attachment_key: item.parentItem?.key || null,
			zotero_library_id: libraryID || null,
			zotero_library_scope: scope,
			zotero_open_uri: deepLink,
			annotation_type: item.annotationType || null,
			annotation_text: item.annotationText || null,
			annotation_comment: item.annotationComment || null,
			annotation_color: item.annotationColor || null,
			annotation_page_label: item.annotationPageLabel || null,
			annotation_position: item.annotationPosition || null,
			notifier: extraData || null,
		});
	},

	startObserving() {
		if (this.observerID) return;
		this.observerID = Zotero.Notifier.registerObserver({
			notify: (event, type, ids, extraData) => {
				if (type !== "item" || !["add", "modify"].includes(event)) return;
				for (let id of ids) {
					let item = Zotero.Items.get(id);
					if (event === "modify" && item?.isNote?.()) {
						this.noteChanged(item, extraData?.[id]).catch(error => this.log("note observer failed: " + error));
					}
					else if (item?.isAnnotation?.()) {
						this.annotationChanged(item, { event, detail: extraData?.[id] })
							.catch(error => this.log("annotation observer failed: " + error));
					}
				}
			},
		}, ["item"], "atr-zotero-native-projection");
		this.log("native note/annotation observer started");
	},

	stopObserving() {
		if (this.observerID) Zotero.Notifier.unregisterObserver(this.observerID);
		this.observerID = null;
	},

	async addToWindow(window) {
		let doc = window.document;
		window.MozXULElement.insertFTLIfNeeded("atr-mainWindow.ftl");
		if (doc.getElementById("atr-zotero-workbench-menu")) return;
		let toolsPopup = doc.getElementById("menu_ToolsPopup");
		if (!toolsPopup) {
			this.log("Tools menu is not ready yet; skipping this window");
			return;
		}
		let menu = doc.createXULElement("menu");
		menu.id = "atr-zotero-workbench-menu";
		menu.setAttribute("label", "ATR Research");
		let popup = doc.createXULElement("menupopup");
		let registry;
		try {
			registry = await this.loadRunRegistry();
		}
		catch (error) {
			let item = doc.createXULElement("menuitem");
			item.setAttribute("label", "配置错误 · 查看详情");
			item.addEventListener("command", () => Services.prompt.alert(window, "ATR Research", String(error)));
			popup.append(item);
			menu.append(popup);
			toolsPopup.append(menu);
			this.log("native topic menu added in degraded mode: " + error);
			await this.appendRuntimeStatus("native_topic_menu_degraded", { error: String(error) });
			return;
		}
		let runs = registry.runs.length ? registry.runs : [await this.defaultRun()];
		runs.sort((left, right) => Number(right.key === registry.activeRun) - Number(left.key === registry.activeRun));
		for (let run of runs) {
			let item = doc.createXULElement("menuitem");
			let roleLabel = {
				CURRENT_RUN: "当前权威",
				HISTORICAL_NAVIGATION: "历史导航",
				LEGACY_CONTINUATION: "迁移链",
				LEGACY_EXPLORATION: "历史探索",
				LEGACY_RUN: "旧版 run",
			}[run.view_role] || run.view_role;
			item.setAttribute("label", roleLabel + " · " + (run.label || run.key));
			item.addEventListener("command", () => this.openTopic(run, window));
			popup.append(item);
		}
		menu.append(popup);
		toolsPopup.append(menu);
		this.log("native topic menu added");
		await this.appendRuntimeStatus("native_topic_menu_added", {
			run_count: runs.length,
			active_run: registry.activeRun,
		});
	},

	async addToAllWindows() {
		for (let window of Zotero.getMainWindows()) {
			if (window.ZoteroPane) await this.addToWindow(window);
		}
	},

	removeFromWindow(window) {
		window.document.getElementById("atr-zotero-workbench-menu")?.remove();
	},

	removeFromAllWindows() {
		for (let window of Zotero.getMainWindows()) {
			if (window.ZoteroPane) this.removeFromWindow(window);
		}
	},

	hooks: {
		async onStartup({ id, rootURI }) {
			ATRZoteroWorkbench.init({ id, rootURI });
			try {
				ATRZoteroWorkbench.activeWorkspace = (await ATRZoteroWorkbench.defaultRun()).workspace;
			}
			catch (error) {
				ATRZoteroWorkbench.log("startup registry unavailable; entering degraded mode: " + error);
			}
			await ATRZoteroWorkbench.appendRuntimeStatus("startup_complete", {
				addon_id: id,
				root_uri: rootURI,
			});
			await ATRZoteroWorkbench.addToAllWindows();
			await ATRZoteroWorkbench.registerItemPane();
			ATRZoteroWorkbench.startObserving();
			if (Zotero.Prefs.get("extensions.atr-zotero-workbench.devSmokeTestOnStartup", true)) {
				let window = Zotero.getMainWindow();
				if (!window) throw new Error("development smoke test requires a main Zotero window");
				await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_test_started");
				let synced = await ATRZoteroWorkbench.openTopic(await ATRZoteroWorkbench.defaultRun(), window);
				let currentProblemObject = (ATRZoteroWorkbench.activeNativeMap?.objects || [])
					.find(object => object.object_kind === "problem_note"
						&& object.review_role !== "HISTORICAL_VERSION");
				let currentCollisionObject = (ATRZoteroWorkbench.activeNativeMap?.objects || [])
					.find(object => object.object_kind === "collision_review_note");
				if (synced) {
					let dockProbeObject = currentProblemObject || (ATRZoteroWorkbench.activeNativeMap?.objects || [])
						.find(object => object.object_kind === "knowledge_note"
							&& object.review_role !== "HISTORICAL_VERSION");
					let probeItem = dockProbeObject
						? await ATRZoteroWorkbench.findMarkedNote(dockProbeObject.marker)
						: synced.note;
					let probeBody = window.document.createElementNS("http://www.w3.org/1999/xhtml", "div");
					let probeSummary = "";
					await ATRZoteroWorkbench.renderItemPane({
						doc: window.document, body: probeBody, item: probeItem,
						setSectionSummary: value => { probeSummary = value; },
					});
					let panels = probeBody.querySelectorAll("details[data-atr-dock-key]");
					if (panels.length !== 4) throw new Error("co-reading dock smoke expected four foldable panels, found " + panels.length);
					let miniGraphs = probeBody.querySelectorAll("svg[aria-label='ATR 当前对象局部关系图']");
					let portfolioGraphs = probeBody.querySelectorAll("svg[aria-label='ATR portfolio 到 program 与历史分支总览图']");
					let isPortfolio = (ATRZoteroWorkbench.activeGraph?.nodes || [])
						.some(node => node.kind === "research_portfolio");
					if (isPortfolio && portfolioGraphs.length !== 1) {
						throw new Error("portfolio dock smoke expected one portfolio route graph, found " + portfolioGraphs.length);
					}
					if (isPortfolio) {
						let programNode = (ATRZoteroWorkbench.activeGraph?.nodes || [])
							.find(node => node.kind === "research_program" && node.data?.child_run_id);
						let childRun = programNode
							? await ATRZoteroWorkbench.runForProgramNode(programNode)
							: null;
						if (!childRun || childRun.run_id !== programNode.data.child_run_id) {
							throw new Error("portfolio program node did not resolve to its registered child authority");
						}
						await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_portfolio_program_target_resolved", {
							program_node_id: programNode.id,
							child_run_id: childRun.run_id,
							view_role: childRun.view_role,
						});
						let childSynced = await ATRZoteroWorkbench.openProgramNode(programNode);
						if (!childSynced || ATRZoteroWorkbench.activeRunRecord?.run_id !== childRun.run_id) {
							throw new Error("portfolio program click path did not open its child topic");
						}
						await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_portfolio_program_opened", {
							program_node_id: programNode.id,
							child_run_id: childRun.run_id,
							topic_note_key: childSynced.note.key,
						});
						let ownerReviewNote = await ATRZoteroWorkbench.openProgramReviewNode(programNode);
						if (!ownerReviewNote || !ATRZoteroWorkbench.markerFromNote(ownerReviewNote).collisionReview) {
							throw new Error("portfolio owner-review path did not open the child collision-review Note");
						}
						await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_portfolio_owner_review_opened", {
							program_node_id: programNode.id,
							child_run_id: childRun.run_id,
							collision_review_note_key: ownerReviewNote.key,
						});
						await ATRZoteroWorkbench.openPortfolio();
						if (!(ATRZoteroWorkbench.activeGraph?.nodes || []).some(node => node.kind === "research_portfolio")) {
							throw new Error("return-to-portfolio path did not restore the portfolio projection");
						}
						await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_portfolio_returned", {
							from_child_run_id: childRun.run_id,
						});
					}
					if (!isPortfolio && miniGraphs.length !== 2) {
						throw new Error("co-reading dock smoke expected two local mini-graphs, found " + miniGraphs.length);
					}
					await ATRZoteroWorkbench.appendRuntimeStatus("co_reading_dock_probe_passed", {
						panel_count: panels.length, mini_graph_count: miniGraphs.length,
						portfolio_graph_count: portfolioGraphs.length, section_summary: probeSummary,
					});
				}
				if (synced && Zotero.Prefs.get("extensions.atr-zotero-workbench.devSmokeFeedbackOnStartup", true)) {
					let reviewNote = currentProblemObject
						? await ATRZoteroWorkbench.findMarkedNote(currentProblemObject.marker)
						: synced.decisionNotes?.[0];
					if (!reviewNote) throw new Error("development feedback smoke test requires a decision Note");
					await ATRZoteroWorkbench.setReviewStance(reviewNote, "QUALIFIES");
					await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_feedback_saved", {
						note_key: reviewNote.key,
						review_stance: "QUALIFIES",
					});
					if (currentCollisionObject) {
						let collisionNote = await ATRZoteroWorkbench.findMarkedNote(currentCollisionObject.marker);
						if (!collisionNote) throw new Error("development owner review smoke requires a collision-review Note");
						await ATRZoteroWorkbench.ensureOwnerRouteReviewTemplate(collisionNote);
						await ATRZoteroWorkbench.setOwnerRouteInput(
							collisionNote,
							"ACCEPT_REFRAME",
							"Development smoke: accept only the surviving bounded claim after checking the linked collision source.",
						);
						await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_owner_route_input_saved", {
							note_key: collisionNote.key,
							disposition: "ACCEPT_REFRAME",
						});
					}
				}
				if (synced && Zotero.Prefs.get("extensions.atr-zotero-workbench.devSmokeReaderAnnotationOnStartup", true)) {
					let pdfPath = Zotero.Prefs.get("extensions.atr-zotero-workbench.devSmokePDFPath", true);
					let nativeResolver = Zotero.Prefs.get("extensions.atr-zotero-workbench.devSmokeNativeResolver", true);
					let preferredSourceID = Zotero.Prefs.get("extensions.atr-zotero-workbench.devSmokePreferredSourceID", true)
						|| currentProblemObject?.linked_source_ids?.[0];
					let sourceIndex = preferredSourceID
						? synced.sources.findIndex(source => source.data?.source_id === preferredSourceID)
						: 0;
					if (sourceIndex < 0) sourceIndex = 0;
					if (!pdfPath && !nativeResolver && !synced.sources?.[sourceIndex]?.data?.pdf_url) {
						sourceIndex = synced.sources.findIndex(source => source.data?.pdf_url);
					}
					let source = synced.sources?.[sourceIndex];
					let sourceItem = synced.items?.[sourceIndex];
					if (!source || !sourceItem) {
						throw new Error("development Reader smoke test requires a mapped source");
					}
					let attachment = pdfPath
						? await Zotero.Attachments.importFromFile({
							file: pdfPath,
							parentItemID: sourceItem.id,
							title: "ATR repository-local Reader smoke fixture",
						})
						: await ATRZoteroWorkbench.ensureReadableAttachment(source, sourceItem);
					if (!attachment) {
						throw new Error("development Reader smoke test could not acquire a readable attachment");
					}
					await ATRZoteroWorkbench.openSourceForCoReading(source, sourceItem);
					let annotation = await Zotero.Annotations.saveFromJSON(attachment, {
						key: Zotero.DataObjectUtilities.generateKey(),
						type: "highlight",
						text: "ATR Reader smoke source span",
						comment: "ATR Reader smoke review comment",
						color: "#ffd400",
						pageLabel: "1",
						sortIndex: "00000|000000|00000",
						position: { pageIndex: 0, rects: [[72, 700, 300, 720]] },
					});
					await Zotero.Promise.delay(250);
					await ATRZoteroWorkbench.openSourceInReader(source, annotation);
					let coReadingNote = await ATRZoteroWorkbench.ensureSourceReviewNote(source, sourceItem);
					await ATRZoteroWorkbench.openThreePaneCoReading(source, annotation);
					let contextMode = window.ZoteroContextPane?.context?.mode;
					if (ATRZoteroWorkbench.readingNoteID !== coReadingNote.id
							|| !ATRZoteroWorkbench.readingNoteSectionID
							|| contextMode !== "item") {
						throw new Error("Reader-centered smoke did not keep the foldable Note and ATR sections together");
					}
					let companionRoot = ATRZoteroWorkbench.companionWindow?.document
						?.getElementById("atr-companion-root");
					let companionPanels = companionRoot?.querySelectorAll("details[data-atr-dock-key]") || [];
					let companionGraphs = companionRoot
						?.querySelectorAll("svg[aria-label='ATR 当前对象局部关系图']") || [];
					await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_three_surface_probe", {
						root_found: !!companionRoot,
						panel_count: companionPanels.length,
						mini_graph_count: companionGraphs.length,
					});
					if (companionPanels.length !== 4 || companionGraphs.length !== 2) {
						throw new Error("three-surface smoke did not render four foldable panels and two local graphs");
					}
					await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_three_surface_coreading_ready", {
						panel_count: companionPanels.length,
						mini_graph_count: companionGraphs.length,
						note_key: coReadingNote.key,
					});
					await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_reader_note_section_ready", {
						note_key: coReadingNote.key,
						attachment_key: attachment.key,
						source_id: source.data?.source_id,
						note_pane_id: ATRZoteroWorkbench.readingNoteSectionID,
						atr_pane_id: ATRZoteroWorkbench.sectionID,
						context_mode: contextMode,
					});
					await ATRZoteroWorkbench.appendRuntimeStatus("dev_smoke_reader_annotation_saved", {
						annotation_key: annotation.key,
						attachment_key: attachment.key,
						source_id: source.data?.source_id,
					});
				}
			}
		},

		async onMainWindowLoad(window) {
			await ATRZoteroWorkbench.addToWindow(window);
		},

		async onMainWindowUnload(window) {
			ATRZoteroWorkbench.removeFromWindow(window);
		},

	async onShutdown() {
			if (ATRZoteroWorkbench.companionWindowAlive()) ATRZoteroWorkbench.companionWindow.close();
			ATRZoteroWorkbench.stopObserving();
			ATRZoteroWorkbench.unregisterReadingNoteSection();
			ATRZoteroWorkbench.unregisterItemPane();
			ATRZoteroWorkbench.removeFromAllWindows();
		},
	},
};
