import { Component, OnInit, OnDestroy, inject, signal, input} from '@angular/core';
import { Api, LogEvent } from '../api';
import { Subscription } from 'rxjs';

interface Row {
  id: string;
  text: string;
  status: string;
  tag: string | null;  
}

@Component({
  imports: [],
  selector: 'app-runner',
  styleUrl: './runner.scss',
  templateUrl: './runner.html',
})

export class Runner implements OnInit, OnDestroy {
  private api = inject(Api);
  private sub?: Subscription;
  running = signal(false);
  rows = signal<Row[]>([]);
  lines = signal<string[]>([]);
  name = input.required<string>();

  ngOnInit() {
    this.sub = this.api.events().subscribe(e => { 
      this.apply(e);
    });
    this.api.status().subscribe(s => {
      this.running.set(s.running);
    });
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
  }

  run (name: string) {
    this.api.run(name).subscribe(() => {
      this.running.set(true);
    });
  }

  stop() {
    this.api.stop().subscribe();
  }

  private apply(e: LogEvent) {
    const id = JSON.stringify(e.song_id);
    if (e.kind === 'song') {
      this.rows.update(r => [...r, { id, text: e.text, status: '', tag: null }]);
    } else if (e.kind === 'status') {
      this.rows.update(r => 
        r.map(row => 
          row.id === id ? { ...row, status: e.text, tag: e.tag } : row
        )
      );
    } else {
      this.lines.update(l => [...l, e.text]);
      if (e.text.startsWith('Finished') || e.text.startsWith('Stopped')) this.running.set(false);
    }
  }
}
