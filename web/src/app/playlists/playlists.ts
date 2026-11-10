import { Component, inject, OnInit} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink, Router} from '@angular/router';
import { Api } from '../api';


@Component({
  imports: [RouterLink],
  selector: 'app-playlists',
  styleUrl: './playlists.scss',
  templateUrl: './playlists.html',
})
export class Playlists implements OnInit {
  private api = inject(Api);
  private router = inject(Router);

  ngOnInit() {
    this.api.settings().subscribe(s => { if (!s.configured) this.router.navigateByUrl('/settings'); });
  }

  // La lista de playists
  playlists = toSignal(this.api.playlists(), {initialValue: []});

  cover(name_playlist: string) {
    return `/api/playlists/${encodeURIComponent( name_playlist )}/cover`;
  }
}
