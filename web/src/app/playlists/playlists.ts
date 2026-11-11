import { Component, inject, OnInit, signal} from '@angular/core';
import { RouterLink, Router} from '@angular/router';
import { Api, Playlist } from '../api';


@Component({
  imports: [RouterLink],
  selector: 'app-playlists',
  styleUrl: './playlists.scss',
  templateUrl: './playlists.html',
})

export class Playlists implements OnInit {
  private api = inject(Api);
  playlists = signal<Playlist[]>([]);
  loading = signal(false);

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.api.playlists().subscribe({
      next: p => { this.playlists.set(p); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
  cover(name_playlist: string) {
    return `/api/playlists/${encodeURIComponent( name_playlist )}/cover`;
  }
}
