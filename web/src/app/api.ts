import { Injectable, inject, Service, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Playlist { 
    name: string;
    cover_url: string | null;
}

export interface Settings {
    configured: boolean;
    soulseek_username: string;
    music_dir: string;
    share_dir: string;
    listen_port: number;
    credentials_file: string;
}

export interface LogEvent {
    kind: 'song' | 'status' | 'line';
    song_id: [string, number] | null;
    text: string;
    tag: string | null;
}

@Injectable({ providedIn: 'root' })
export class Api {
    private http = inject(HttpClient);
    private base = '/api';
    running = signal(false);

    playlists(){
        return this.http.get<Playlist[]>(`${this.base}/playlists`);
    }
    settings(){
        return this.http.get<Settings>(`${this.base}/settings`);
    }
    log(){
        return this.http.get(`${this.base}/log`, { responseType: 'text' });
    }
    saveSettings(body: Omit<Settings, 'configured'> & {soulseek_password: string}) {
        return this.http.post(`${this.base}/settings`, body);
    }
    run(name: string){
        return this.http.post(`${this.base}/run/${encodeURIComponent(name)}`, null);
    }
    stop(){
        return this.http.post(`${this.base}/stop`, null);
    }
    status(){
        return this.http.get<{running: boolean}>(`${this.base}/status`);
    }
    pickFolder(){
        return this.http.post<{path: string}>(`${this.base}/pick-folder`, null);
    }
    pickFile(){
        return this.http.post<{path: string}>(`${this.base}/pick-file`, null);
    }
    events(): Observable<LogEvent> {
        return new Observable(subscriber => {
            const source = new EventSource(`${this.base}/events`);
            source.onmessage = e => {
                subscriber.next(JSON.parse(e.data));
            };
            source.onerror = () => {
                subscriber.error(new Error('Events stream lost'));
            };
            return () => source.close();
        });
    }
}